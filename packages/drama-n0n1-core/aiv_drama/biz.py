"""Gaps 10–18: segment video, outputs, rough-cut, seams, subtitles, bed, TTS, L reviews, spend.

L1/L2/L3 are review layers. They are never mapped or back-signed onto G1b/G2/G3.
ForcePass=never. API keys are never accepted or persisted.
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any

from aiv_drama.biz_models import (
    AudioBedRequest,
    AudioVoiceRequest,
    CostEntryRequest,
    OpenItemCloseRequest,
    OpenItemConclusionRequest,
    OpenItemConsentRequest,
    OpenItemCreateRequest,
    OutputRegisterRequest,
    RedrawConsentRequest,
    ReviewCreateRequest,
    RoughCutRequest,
    SeamMeasureRequest,
    SegmentVideoRequest,
    SubtitleWriteRequest,
)
from aiv_drama.errors import AppError
from aiv_drama.secrets import reject_secret_fields
from aiv_drama.store import atomic_write_text
from aiv_drama.validate import FORCE_KEYS, now_iso, validate_ep
from aiv_drama_n4.projection import read_prompts_jsonl
from aiv_drama_n4.seedance import generate_seedance_segment
from aiv_schema.models import GATE_G3, NODE_DN4

LOOK_ATTEMPT_CAP = 2
SPEND_CAP = 60
OPEN_ITEM_STATES = frozenset({"blocks_l2", "waiting_on_user", "non_blocking", "closed"})
SEAM_JOIN_LIMIT_S = 0.08
SEAM_LOUD_LIMIT_DB = 3.0
MD5_RE_LEN = 32
LOOK_NON_COUNT_CODES = frozenset(
    {
        "material_bind",
        "look_card_incomplete",
        "scene_look_forbidden",
        "cards_empty",
        "card_id_not_in_cast",
        "force_pass_forbidden",
        "validation",
        "attempt_cap",
        "over_cap",
        "redraw_needs_user",
        "locked",
        "upstream_unlocked",
        "episode_abandoned",
        "not_found",
        "wrong_profile",
    }
)


def empty_cost() -> dict[str, Any]:
    return {"cap": SPEND_CAP, "spent": 0.0, "currency": "CNY", "entries": {}, "order": []}


def empty_look_ledger() -> dict[str, Any]:
    return {
        "attempts_used": 0,
        "attempts": [],
        "needs_redraw_consent": False,
        "user_redraw_consent": None,
    }


def empty_segment_videos() -> dict[str, Any]:
    return {"episode_stopped": False, "failed_segment_id": None, "segments": {}}


def _md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def reject_force_keys_biz(body: dict[str, Any] | None) -> None:
    if not isinstance(body, dict):
        return
    for key in FORCE_KEYS:
        if key in body:
            raise AppError(
                400,
                "force_pass_forbidden",
                "ForcePass=never",
                field=key,
                node="biz",
            )


def reject_blocking_boolean(body: dict[str, Any] | None) -> None:
    if isinstance(body, dict) and "blocking" in body:
        raise AppError(
            400,
            "validation",
            "open items use four states; no blocking boolean",
            field="blocking",
        )


class DramaBizOps:
    """Mixin: post-assemble business APIs. Does not confirm or rewrite G gates."""

    def _ensure_biz_fields(self, rec: dict[str, Any]) -> None:
        rec.setdefault("look_ledger", empty_look_ledger())
        rec.setdefault("segment_videos", empty_segment_videos())
        rec.setdefault("outputs", {"by_md5": {}, "order": []})
        rec.setdefault("rough_cuts", {})
        rec.setdefault("seam_measures", {})
        rec.setdefault("subtitles", {})
        rec.setdefault("audio_beds", {})
        rec.setdefault("audio_voices", {})
        rec.setdefault("reviews", {"by_id": {}, "order": []})
        rec.setdefault("open_items", {"by_no": {}, "order": []})
        rec["look_ledger"].setdefault("attempts_used", 0)
        rec["look_ledger"].setdefault("attempts", [])
        rec["look_ledger"].setdefault("needs_redraw_consent", False)
        rec["look_ledger"].setdefault("user_redraw_consent", None)
        # ¥60 lives on the project. Episode rec.cost is not a second ledger.

    def _ensure_project_cost(self, proj: dict[str, Any]) -> None:
        proj.setdefault("cost", empty_cost())
        proj["cost"].setdefault("cap", SPEND_CAP)
        proj["cost"].setdefault("spent", 0.0)
        proj["cost"].setdefault("entries", {})
        proj["cost"].setdefault("order", [])

    def _look_ledger(self, rec: dict[str, Any]) -> dict[str, Any]:
        self._ensure_biz_fields(rec)
        return rec["look_ledger"]

    def look_attempts_used(self, rec: dict[str, Any]) -> int:
        return int(self._look_ledger(rec).get("attempts_used") or 0)

    def require_look_attempt_available(self, rec: dict[str, Any], **_ignored: Any) -> None:
        ledger = self._look_ledger(rec)
        used = int(ledger.get("attempts_used") or 0)
        if used >= LOOK_ATTEMPT_CAP:
            raise AppError(
                409,
                "attempt_cap",
                "look attempt cap reached (2 including failures)",
                attempts_used=LOOK_ATTEMPT_CAP,
                cap=LOOK_ATTEMPT_CAP,
            )
        if ledger.get("needs_redraw_consent") and not self._recorded_user_redraw_consent(ledger):
            raise AppError(
                409,
                "redraw_needs_user",
                "a failed redraw requires a recorded user consent before the next look",
                attempts_used=used,
                needs_redraw_consent=True,
            )

    @staticmethod
    def _recorded_user_redraw_consent(ledger: dict[str, Any]) -> bool:
        consent = ledger.get("user_redraw_consent")
        return isinstance(consent, dict) and consent.get("user") is True

    def record_look_attempt(self, rec: dict[str, Any], *, ok: bool, card_id: str | None = None) -> int:
        ledger = self._look_ledger(rec)
        if ledger.get("needs_redraw_consent"):
            ledger["user_redraw_consent"] = None
        ledger["attempts_used"] = int(ledger.get("attempts_used") or 0) + 1
        ledger.setdefault("attempts", []).append(
            {"at": now_iso(), "ok": bool(ok), "card_id": card_id}
        )
        ledger["needs_redraw_consent"] = not ok
        return int(ledger["attempts_used"])

    def record_redraw_consent(
        self,
        project_id: str,
        ep: str,
        body: RedrawConsentRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_biz(raw)
        reject_secret_fields(raw)
        req = body or RedrawConsentRequest.model_validate(raw or {})
        op = f"redraw_consent:{project_id}:{ep}"
        cached = self._idem_get(idempotency_key, op)
        if cached:
            return cached
        if req.user is not True:
            raise AppError(
                409,
                "redraw_needs_user",
                "redraw consent must be an explicit user record; engineering cannot grant it",
            )
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        ledger = self._look_ledger(rec)
        ledger["user_redraw_consent"] = {"user": True, "actor": req.actor, "at": now_iso()}
        self._touch_episode(rec)
        self._commit(rec)
        env = {"ok": True, "user": True, "recorded": True}
        return self._idem_put(idempotency_key, op, env)

    def _project_cost_bucket(self, project_id: str) -> dict[str, Any]:
        proj = self._project(project_id)
        self._ensure_project_cost(proj)
        return proj["cost"]

    def _cost_snapshot_from_bucket(self, bucket: dict[str, Any]) -> dict[str, Any]:
        cap = float(bucket.get("cap") or SPEND_CAP)
        spent = float(bucket.get("spent") or 0.0)
        remaining = max(0.0, cap - spent)
        return {
            "spent": spent,
            "cap": cap,
            "remaining": remaining,
            "blocked": remaining <= 0,
            "currency": bucket.get("currency") or "CNY",
        }

    def cost_snapshot_project(self, project_id: str) -> dict[str, Any]:
        return self._cost_snapshot_from_bucket(self._project_cost_bucket(project_id))

    def generation_blocked(self, project_id: str, ep: str | None = None) -> dict[str, Any]:
        """Project-wide spend snapshot. `ep` is attribution only; there is no per-episode cap."""
        return self.cost_snapshot_project(project_id)

    def _require_generation_budget(self, project_id: str, ep: str | None = None) -> None:
        snap = self.generation_blocked(project_id, ep)
        if snap["blocked"]:
            raise AppError(
                409,
                "over_cap",
                "spend ceiling reached; generation is blocked",
                spent=snap["spent"],
                cap=snap["cap"],
                remaining=snap["remaining"],
                blocked=True,
            )

    def _output_by_md5(self, rec: dict[str, Any], md5: str) -> dict[str, Any] | None:
        self._ensure_biz_fields(rec)
        found = (rec["outputs"].get("by_md5") or {}).get(md5)
        return deepcopy(found) if found else None

    def _require_registered_md5(self, rec: dict[str, Any], md5: str, *, code: str = "subject_mismatch") -> dict[str, Any]:
        row = self._output_by_md5(rec, md5)
        if not row:
            raise AppError(409, code, "md5 is not a registered output", md5=md5)
        return row

    def _video_stream_known(self, rec: dict[str, Any], md5: str) -> bool:
        row = self._output_by_md5(rec, md5)
        if row and row.get("kind") in {"segment_video", "rough_cut"}:
            return True
        segs = (rec.get("segment_videos") or {}).get("segments") or {}
        return any(item.get("output_md5") == md5 for item in segs.values() if isinstance(item, dict))

    def _n4_assembled_lines(self, rec: dict[str, Any]) -> list[dict[str, Any]]:
        n4 = rec.get("n4") or {}
        if not n4.get("started"):
            return []
        ep = rec["episode"]["episode_id"]
        project_id = rec["episode"]["project_id"]
        episode_dir = self.store.episode_dir(project_id, ep)
        return read_prompts_jsonl(episode_dir, ep)

    def _find_assembled_line(self, rec: dict[str, Any], segment_id: str) -> dict[str, Any] | None:
        for row in self._n4_assembled_lines(rec):
            if row.get("shot_id") == segment_id:
                return row
        return None

    def _line_prompt_shas(self, line: dict[str, Any]) -> set[str]:
        out: set[str] = set()
        prompt = line.get("prompt") or ""
        if prompt:
            out.add(_sha256_text(prompt))
        fp = line.get("fingerprint")
        if isinstance(fp, str) and fp:
            out.add(fp)
        extra = line.get("prompt_sha256")
        if isinstance(extra, str) and extra:
            out.add(extra)
        return out

    def _write_bytes(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    def _cache_error(self, idempotency_key: str | None, op: str, exc: AppError) -> None:
        put_err = getattr(self, "_idem_put_error", None)
        if callable(put_err):
            put_err(idempotency_key, op, exc)

    # ----- 10 Seedance per-segment video -------------------------------------------

    def generate_segment_video(
        self,
        project_id: str,
        ep: str,
        segment_id: str,
        body: SegmentVideoRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        post: Any | None = None,
        get: Any | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_biz(raw)
        reject_secret_fields(raw)
        req = body or SegmentVideoRequest.model_validate(raw or {})
        op = f"segment_video:{project_id}:{ep}:{segment_id}"
        cached = self._idem_get(idempotency_key, op)
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        self._ensure_biz_fields(rec)
        g3 = rec.get("gate_g3") or {}
        n4 = rec.get("n4") or {}
        if not g3.get("locked") or not n4.get("started"):
            exc = AppError(
                409,
                "upstream_unlocked",
                "N4 is not assembled or G3 is not locked",
                node=NODE_DN4,
                gate=GATE_G3,
            )
            self._cache_error(idempotency_key, op, exc)
            raise exc
        videos = rec["segment_videos"]
        existing = (videos.get("segments") or {}).get(segment_id)
        if existing:
            exc = AppError(
                409,
                "already_attempted",
                "this segment already used its only attempt",
                segment_id=segment_id,
                attempt=1,
                status=existing.get("status"),
            )
            self._cache_error(idempotency_key, op, exc)
            raise exc
        if videos.get("episode_stopped"):
            exc = AppError(
                409,
                "episode_stopped",
                "a prior segment failed; the episode is stopped",
                failed_segment_id=videos.get("failed_segment_id"),
                segment_id=segment_id,
            )
            self._cache_error(idempotency_key, op, exc)
            raise exc
        line = self._find_assembled_line(rec, segment_id)
        if line is None:
            exc = AppError(409, "prompt_mismatch", "segment is not on the assembled N4 sheet", segment_id=segment_id)
            self._cache_error(idempotency_key, op, exc)
            raise exc
        allowed = self._line_prompt_shas(line)
        if req.prompt_sha256 not in allowed:
            exc = AppError(
                409,
                "prompt_mismatch",
                "prompt_sha256 does not match the assembled line",
                segment_id=segment_id,
            )
            self._cache_error(idempotency_key, op, exc)
            raise exc
        self._require_generation_budget(project_id, rec["episode"]["episode_id"])

        def _fail(status: str, *, http_exc: AppError | None = None) -> dict[str, Any]:
            row = {
                "segment_id": segment_id,
                "status": "failed",
                "attempt": 1,
                "output_md5": None,
                "output_path": None,
                "provider_request_id": None,
                "prompt_sha256": req.prompt_sha256,
                "ref_md5s": list(req.ref_md5s),
                "tool_profile": "seedance_2",
                "actor": req.actor,
                "at": now_iso(),
            }
            videos["segments"][segment_id] = row
            videos["episode_stopped"] = True
            videos["failed_segment_id"] = segment_id
            self._touch_episode(rec)
            self._commit(rec)
            if http_exc is not None:
                self._cache_error(idempotency_key, op, http_exc)
                raise http_exc
            env = {"ok": True, **row}
            return self._idem_put(idempotency_key, op, env)

        try:
            result = generate_seedance_segment(
                api_key=getattr(self.settings, "ark_api_key", None),
                prompt=str(line.get("prompt") or ""),
                duration_s=int(line.get("duration_s") or 5),
                aspect=str(line.get("aspect") or "9:16"),
                post=post,
                get=get,
            )
        except AppError as exc:
            if exc.code == "provider":
                return _fail("failed", http_exc=exc)
            self._cache_error(idempotency_key, op, exc)
            raise

        dest = self.store.episode_dir(project_id, rec["episode"]["episode_id"]) / "segments" / f"{segment_id}.mp4"
        self._write_bytes(dest, result["bytes"])
        row = {
            "segment_id": segment_id,
            "status": "succeeded",
            "attempt": 1,
            "output_md5": result["output_md5"],
            "output_path": str(dest),
            "provider_request_id": result.get("provider_request_id"),
            "prompt_sha256": req.prompt_sha256,
            "ref_md5s": list(req.ref_md5s),
            "tool_profile": "seedance_2",
            "actor": req.actor,
            "at": now_iso(),
        }
        videos["segments"][segment_id] = row
        self._touch_episode(rec)
        self._commit(rec)
        env = {"ok": True, **row}
        return self._idem_put(idempotency_key, op, env)

    # ----- 11 artifact md5 registration --------------------------------------------

    def register_output(
        self,
        project_id: str,
        ep: str,
        body: OutputRegisterRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_biz(raw)
        reject_secret_fields(raw)
        req = body or OutputRegisterRequest.model_validate(raw or {})
        op = f"output:{project_id}:{ep}:{req.kind}:{req.md5}"
        cached = self._idem_get(idempotency_key, op)
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        self._ensure_biz_fields(rec)
        md5 = req.md5.lower()
        if len(md5) != MD5_RE_LEN or any(ch not in "0123456789abcdef" for ch in md5):
            raise AppError(400, "validation", "md5 must be 32 hex chars", field="md5")
        existing = self._output_by_md5(rec, md5)
        if existing:
            env = {"ok": True, "output_id": existing["output_id"], "md5": existing["md5"], "registered_at": existing["registered_at"]}
            return self._idem_put(idempotency_key, op, env)
        path = Path(req.path)
        if not path.is_file():
            raise AppError(400, "validation", "output path is not a file", field="path")
        raw_bytes = path.read_bytes()
        actual = _md5_hex(raw_bytes)
        if actual != md5:
            raise AppError(409, "md5_mismatch", "server md5 does not match request", expected=md5, actual=actual)
        if int(req.bytes) != len(raw_bytes):
            raise AppError(400, "validation", "bytes does not match file size", field="bytes", expected=len(raw_bytes))
        ts = now_iso()
        output_id = f"{req.kind}:{md5}"
        row = {
            "output_id": output_id,
            "kind": req.kind,
            "path": str(path),
            "md5": md5,
            "bytes": len(raw_bytes),
            "parent_md5": req.parent_md5,
            "actor": req.actor,
            "registered_at": ts,
        }
        rec["outputs"]["by_md5"][md5] = row
        rec["outputs"]["order"].append(md5)
        self._touch_episode(rec)
        self._commit(rec)
        env = {"ok": True, "output_id": output_id, "md5": md5, "registered_at": ts}
        return self._idem_put(idempotency_key, op, env)

    # ----- 12 rough-cut versions ---------------------------------------------------

    def create_rough_cut(
        self,
        project_id: str,
        ep: str,
        body: RoughCutRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_biz(raw)
        reject_secret_fields(raw)
        req = body or RoughCutRequest.model_validate(raw or {})
        op = f"rough_cut:{project_id}:{ep}:{req.version}"
        cached = self._idem_get(idempotency_key, op)
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        self._ensure_biz_fields(rec)
        existing = rec["rough_cuts"].get(req.version)
        if existing:
            same = (
                existing.get("video_stream_md5") == req.video_stream_md5
                and existing.get("audio_md5") == req.audio_md5
                and (existing.get("subtitle_md5") or None) == (req.subtitle_md5 or None)
            )
            if same:
                env = {
                    "ok": True,
                    "version": existing["version"],
                    "output_md5": existing["output_md5"],
                    "video_stream_md5": existing["video_stream_md5"],
                    "framemd5": existing["framemd5"],
                }
                return self._idem_put(idempotency_key, op, env)
            raise AppError(409, "version_exists", "rough-cut version already exists; never overwrite", version=req.version)
        if not self._video_stream_known(rec, req.video_stream_md5):
            raise AppError(
                409,
                "video_stream_mismatch",
                "video_stream_md5 is not the locked video stream",
                video_stream_md5=req.video_stream_md5,
            )
        dest = self.store.episode_dir(project_id, rec["episode"]["episode_id"]) / "rough-cuts" / f"{req.version}.json"
        if dest.exists():
            raise AppError(409, "version_exists", "rough-cut file already exists; never overwrite", version=req.version)
        payload = {
            "version": req.version,
            "video_stream_md5": req.video_stream_md5,
            "audio_md5": req.audio_md5,
            "subtitle_md5": req.subtitle_md5,
            "parent_version": req.parent_version,
            "actor": req.actor,
            "created_at": now_iso(),
        }
        body_text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        atomic_write_text(dest, body_text)
        output_md5 = _md5_hex(body_text.encode("utf-8"))
        framemd5 = _md5_hex(
            f"{req.video_stream_md5}:{req.audio_md5}:{req.subtitle_md5 or ''}:{req.version}".encode("utf-8")
        )
        row = {
            **payload,
            "output_md5": output_md5,
            "framemd5": framemd5,
            "path": str(dest),
        }
        rec["rough_cuts"][req.version] = row
        self._touch_episode(rec)
        self._commit(rec)
        env = {
            "ok": True,
            "version": req.version,
            "output_md5": output_md5,
            "video_stream_md5": req.video_stream_md5,
            "framemd5": framemd5,
        }
        return self._idem_put(idempotency_key, op, env)

    # ----- 13 seam measurement -----------------------------------------------------

    def measure_seams(
        self,
        project_id: str,
        ep: str,
        version: str,
        body: SeamMeasureRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_biz(raw)
        reject_secret_fields(raw)
        req = body or SeamMeasureRequest.model_validate(raw or {})
        if req.version and req.version != version:
            raise AppError(400, "validation", "path version and body version differ", field="version")
        op = f"seams:{project_id}:{ep}:{version}:{req.ruleset_md5}"
        cached = self._idem_get(idempotency_key, op)
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        self._ensure_biz_fields(rec)
        cut = rec["rough_cuts"].get(version)
        if not cut:
            raise AppError(404, "not_found", "rough-cut version not found", version=version)
        bucket = rec["seam_measures"].setdefault(version, {})
        prior_keys = [k for k in bucket if k != req.ruleset_md5]
        if prior_keys and req.ruleset_md5 not in bucket:
            raise AppError(
                409,
                "ruleset_mismatch",
                "ruleset_md5 does not match the bound measurement ruleset",
                expected=prior_keys[0],
            )
        seams = self._compute_seams(rec, cut)
        passed = all(item.get("pass") for item in seams)
        record = {
            "version": version,
            "ruleset_md5": req.ruleset_md5,
            "pass": passed,
            "seams": seams,
            "actor": req.actor,
            "measured_at": now_iso(),
        }
        bucket.setdefault(req.ruleset_md5, []).append(record)
        first = bucket[req.ruleset_md5][0]
        # Re-measure must stay consistent with the first result.
        record["seams"] = deepcopy(first["seams"])
        record["pass"] = first["pass"]
        self._touch_episode(rec)
        self._commit(rec)
        env = {"ok": True, "version": version, "pass": first["pass"], "seams": deepcopy(first["seams"])}
        return self._idem_put(idempotency_key, op, env)

    def _load_cut_media(self, rec: dict[str, Any], cut: dict[str, Any]) -> tuple[bytes, bytes, bytes]:
        cut_path = Path(str(cut.get("path") or ""))
        if not cut_path.is_file():
            raise AppError(
                409,
                "subject_mismatch",
                "rough-cut file is missing; cannot measure seams",
                version=cut.get("version"),
            )
        cut_bytes = cut_path.read_bytes()
        video_bytes = b""
        audio_bytes = b""
        video_row = self._output_by_md5(rec, str(cut.get("video_stream_md5") or ""))
        if video_row:
            video_path = Path(str(video_row.get("path") or ""))
            if video_path.is_file():
                video_bytes = video_path.read_bytes()
        audio_row = self._output_by_md5(rec, str(cut.get("audio_md5") or ""))
        if audio_row:
            audio_path = Path(str(audio_row.get("path") or ""))
            if audio_path.is_file():
                audio_bytes = audio_path.read_bytes()
        return cut_bytes, video_bytes, audio_bytes

    @staticmethod
    def _bytes_rms(data: bytes) -> float:
        if not data:
            return 1e-12
        acc = 0.0
        for value in data:
            sample = (value - 128) / 128.0
            acc += sample * sample
        return math.sqrt(acc / len(data)) or 1e-12

    def _compute_seams(self, rec: dict[str, Any], cut: dict[str, Any]) -> list[dict[str, Any]]:
        """Measure the rough-cut product. ruleset_md5 only binds 口径, never the values."""
        cut_bytes, video_bytes, audio_bytes = self._load_cut_media(rec, cut)
        product = cut_bytes + video_bytes
        if cut_bytes and video_bytes:
            join_left, join_right = cut_bytes, video_bytes
        else:
            mid = max(len(product) // 2, 1)
            join_left, join_right = product[:mid], product[mid:]
        left_rms = self._bytes_rms(join_left)
        right_rms = self._bytes_rms(join_right)
        join = abs(left_rms - right_rms) / max(left_rms, right_rms) * 0.05
        loud_src = audio_bytes or product
        loud_mid = max(len(loud_src) // 2, 1)
        loud = abs(
            20.0
            * math.log10(self._bytes_rms(loud_src[loud_mid:]) / self._bytes_rms(loud_src[:loud_mid]))
        )
        at_s = max((len(video_bytes) or len(cut_bytes)) / 48000.0, 0.04)
        return [
            {
                "at_s": at_s,
                "metric": "join_delta_s",
                "value": join,
                "limit": SEAM_JOIN_LIMIT_S,
                "pass": join <= SEAM_JOIN_LIMIT_S,
            },
            {
                "at_s": at_s,
                "metric": "loudness_jump_db",
                "value": loud,
                "limit": SEAM_LOUD_LIMIT_DB,
                "pass": loud <= SEAM_LOUD_LIMIT_DB,
            },
        ]

    # ----- 14 subtitles ------------------------------------------------------------

    def put_subtitles(
        self,
        project_id: str,
        ep: str,
        version: str,
        body: SubtitleWriteRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_biz(raw)
        reject_secret_fields(raw)
        req = body or SubtitleWriteRequest.model_validate(raw or {})
        if req.version and req.version != version:
            raise AppError(400, "validation", "path version and body version differ", field="version")
        op = f"subtitles:{project_id}:{ep}:{version}"
        cached = self._idem_get(idempotency_key, op)
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        self._ensure_biz_fields(rec)
        for point in req.in_points:
            if point.in_s >= point.out_s:
                raise AppError(400, "validation", "in point is later than out point", field="in_points")
        burned = [
            cut["version"]
            for cut in rec["rough_cuts"].values()
            if isinstance(cut, dict) and cut.get("subtitle_md5") == req.body_sha256
        ]
        existing = rec["subtitles"].get(version)
        if existing:
            if existing.get("body_sha256") == req.body_sha256:
                env = {
                    "ok": True,
                    "version": version,
                    "body_sha256": existing["body_sha256"],
                    "line_count": existing["line_count"],
                }
                return self._idem_put(idempotency_key, op, env)
            if existing.get("body_sha256") in {
                cut.get("subtitle_md5") for cut in rec["rough_cuts"].values() if isinstance(cut, dict)
            }:
                raise AppError(
                    409,
                    "version_exists",
                    "this subtitle version is already burned into a rough-cut",
                    version=version,
                )
            raise AppError(409, "version_exists", "subtitle version exists; use a new version", version=version)
        if burned and existing is None:
            pass
        row = {
            "version": version,
            "body_sha256": req.body_sha256,
            "in_points": [p.model_dump() for p in req.in_points],
            "line_count": len(req.in_points),
            "actor": req.actor,
            "updated_at": now_iso(),
        }
        rec["subtitles"][version] = row
        self._touch_episode(rec)
        self._commit(rec)
        env = {"ok": True, "version": version, "body_sha256": req.body_sha256, "line_count": row["line_count"]}
        return self._idem_put(idempotency_key, op, env)

    # ----- 15 audio bed ------------------------------------------------------------

    def create_audio_bed(
        self,
        project_id: str,
        ep: str,
        body: AudioBedRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_biz(raw)
        reject_secret_fields(raw)
        req = body or AudioBedRequest.model_validate(raw or {})
        op = f"audio_bed:{project_id}:{ep}:{req.version}"
        cached = self._idem_get(idempotency_key, op)
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        self._ensure_biz_fields(rec)
        for source in req.sources:
            if not self._output_by_md5(rec, source.md5):
                raise AppError(422, "source_unregistered", "bed source is not a registered output", md5=source.md5)
        material = json.dumps(
            {
                "version": req.version,
                "spec_md5": req.spec_md5,
                "sources": [s.model_dump() for s in req.sources],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        bed_md5 = _md5_hex(material.encode("utf-8"))
        existing = rec["audio_beds"].get(req.version)
        if existing:
            if existing.get("bed_md5") == bed_md5:
                env = {
                    "ok": True,
                    "version": req.version,
                    "bed_md5": existing["bed_md5"],
                    "sample_rate": existing["sample_rate"],
                    "channels": existing["channels"],
                }
                return self._idem_put(idempotency_key, op, env)
            raise AppError(409, "version_exists", "audio bed version exists; never overwrite", version=req.version)
        dest = self.store.episode_dir(project_id, rec["episode"]["episode_id"]) / "audio" / f"bed-{req.version}.json"
        if dest.exists():
            raise AppError(409, "version_exists", "audio bed file exists; never overwrite", version=req.version)
        atomic_write_text(dest, material + "\n")
        row = {
            "version": req.version,
            "spec_md5": req.spec_md5,
            "sources": [s.model_dump() for s in req.sources],
            "bed_md5": bed_md5,
            "sample_rate": 48000,
            "channels": 2,
            "path": str(dest),
            "actor": req.actor,
            "created_at": now_iso(),
        }
        rec["audio_beds"][req.version] = row
        self._touch_episode(rec)
        self._commit(rec)
        env = {"ok": True, "version": req.version, "bed_md5": bed_md5, "sample_rate": 48000, "channels": 2}
        return self._idem_put(idempotency_key, op, env)

    # ----- 16 TTS placement (no synthesis) -----------------------------------------

    def place_voice_line(
        self,
        project_id: str,
        ep: str,
        body: AudioVoiceRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_biz(raw)
        reject_secret_fields(raw)
        req = body or AudioVoiceRequest.model_validate(raw or {})
        key = f"{req.version}:{req.line_no}"
        op = f"audio_voice:{project_id}:{ep}:{key}:{req.take_md5}"
        cached = self._idem_get(idempotency_key, op)
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        self._ensure_biz_fields(rec)
        if req.in_s < 0:
            raise AppError(400, "validation", "in_s must be >= 0", field="in_s")
        take = self._output_by_md5(rec, req.take_md5)
        if not take:
            raise AppError(409, "take_unregistered", "take_md5 is not a registered output", md5=req.take_md5)
        existing = rec["audio_voices"].get(key)
        if existing:
            if existing.get("take_md5") == req.take_md5:
                env = {
                    "ok": True,
                    "version": req.version,
                    "line_no": req.line_no,
                    "placed_md5": existing["placed_md5"],
                }
                return self._idem_put(idempotency_key, op, env)
            raise AppError(409, "version_exists", "voice line version exists; never overwrite", version=req.version)
        placed_md5 = _md5_hex(f"{req.take_md5}:{req.version}:{req.line_no}:{req.in_s}".encode("utf-8"))
        row = {
            "version": req.version,
            "line_no": req.line_no,
            "take_md5": req.take_md5,
            "in_s": req.in_s,
            "placed_md5": placed_md5,
            "actor": req.actor,
            "created_at": now_iso(),
            "synthesized": False,
        }
        rec["audio_voices"][key] = row
        self._touch_episode(rec)
        self._commit(rec)
        env = {"ok": True, "version": req.version, "line_no": req.line_no, "placed_md5": placed_md5}
        return self._idem_put(idempotency_key, op, env)

    # ----- 17 L1/L2/L3 + open items (not G gates) ----------------------------------

    def create_review(
        self,
        project_id: str,
        ep: str,
        body: ReviewCreateRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_biz(raw)
        reject_secret_fields(raw)
        req = body or ReviewCreateRequest.model_validate(raw or {})
        op = f"review:{project_id}:{ep}:{req.level}:{req.subject_md5}:{req.actor}"
        cached = self._idem_get(idempotency_key, op)
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        self._ensure_biz_fields(rec)
        self._require_registered_md5(rec, req.subject_md5, code="subject_mismatch")
        if req.level == "L2" and req.verdict == "pass" and self._blocks_l2_open(rec):
            raise AppError(
                409,
                "blocks_l2_open",
                "blocking open items remain; L2 cannot pass",
                level="L2",
            )
        review_id = f"{req.level}:{req.subject_md5}:{req.actor}"
        existing = rec["reviews"]["by_id"].get(review_id)
        if existing:
            env = {"ok": True, "review_id": existing["review_id"], "state": existing["verdict"]}
            return self._idem_put(idempotency_key, op, env)
        row = {
            "review_id": review_id,
            "level": req.level,
            "subject_md5": req.subject_md5,
            "verdict": req.verdict,
            "actor": req.actor,
            "created_at": now_iso(),
            "gate": None,
        }
        rec["reviews"]["by_id"][review_id] = row
        rec["reviews"]["order"].append(review_id)
        self._touch_episode(rec)
        self._commit(rec)
        env = {"ok": True, "review_id": review_id, "state": req.verdict}
        return self._idem_put(idempotency_key, op, env)

    def _blocks_l2_open(self, rec: dict[str, Any]) -> bool:
        items = (rec.get("open_items") or {}).get("by_no") or {}
        return any(isinstance(item, dict) and item.get("state") == "blocks_l2" for item in items.values())

    def create_open_item(
        self,
        project_id: str,
        ep: str,
        body: OpenItemCreateRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_biz(raw)
        reject_secret_fields(raw)
        reject_blocking_boolean(raw)
        req = body or OpenItemCreateRequest.model_validate(raw or {})
        op = f"open_item:{project_id}:{ep}:{req.item_no}"
        cached = self._idem_get(idempotency_key, op)
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        self._ensure_biz_fields(rec)
        if req.review_id not in rec["reviews"]["by_id"]:
            raise AppError(409, "subject_mismatch", "review_id is not a recorded review", review_id=req.review_id)
        existing = rec["open_items"]["by_no"].get(str(req.item_no))
        if existing:
            env = {"ok": True, "item_no": existing["item_no"], "state": existing["state"]}
            return self._idem_put(idempotency_key, op, env)
        if req.state == "closed":
            raise AppError(
                409,
                "close_conditions",
                "cannot create as closed unless close conditions are already met",
                item_no=req.item_no,
            )
        row = {
            "item_no": req.item_no,
            "review_id": req.review_id,
            "state": req.state,
            "owner": req.owner,
            "text": req.text,
            "created_at": now_iso(),
            "conclusion": None,
            "recorded_conclusion": None,
            "recorded_user": None,
            "file_md5": None,
        }
        rec["open_items"]["by_no"][str(req.item_no)] = row
        rec["open_items"]["order"].append(req.item_no)
        self._touch_episode(rec)
        self._commit(rec)
        env = {"ok": True, "item_no": req.item_no, "state": req.state}
        return self._idem_put(idempotency_key, op, env)

    def record_open_item_consent(
        self,
        project_id: str,
        ep: str,
        item_no: int,
        body: OpenItemConsentRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_biz(raw)
        reject_secret_fields(raw)
        req = body or OpenItemConsentRequest.model_validate(raw or {})
        op = f"open_item_consent:{project_id}:{ep}:{item_no}"
        cached = self._idem_get(idempotency_key, op)
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        self._ensure_biz_fields(rec)
        item = rec["open_items"]["by_no"].get(str(item_no))
        if not item:
            raise AppError(404, "not_found", "open item not found", item_no=item_no)
        # Worker-callable: request user/actor never become recorded_user.
        env = {
            "ok": True,
            "item_no": item_no,
            "state": item.get("state"),
            "recorded": False,
        }
        return self._idem_put(idempotency_key, op, env)

    def record_open_item_conclusion(
        self,
        project_id: str,
        ep: str,
        item_no: int,
        body: OpenItemConclusionRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_biz(raw)
        reject_secret_fields(raw)
        req = body or OpenItemConclusionRequest.model_validate(raw or {})
        op = f"open_item_conclusion:{project_id}:{ep}:{item_no}:{req.conclusion}"
        cached = self._idem_get(idempotency_key, op)
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        self._ensure_biz_fields(rec)
        item = rec["open_items"]["by_no"].get(str(item_no))
        if not item:
            raise AppError(404, "not_found", "open item not found", item_no=item_no)
        if item.get("state") == "closed":
            env = {
                "ok": True,
                "item_no": item_no,
                "state": "closed",
                "recorded": True,
            }
            return self._idem_put(idempotency_key, op, env)
        prior = item.get("recorded_conclusion")
        incoming = {
            "conclusion": req.conclusion,
            "actor": req.actor,
            "user": False,
            "at": now_iso(),
        }
        if isinstance(prior, dict):
            if prior.get("conclusion") == incoming["conclusion"]:
                env = {"ok": True, "item_no": item_no, "state": item["state"], "recorded": True}
                return self._idem_put(idempotency_key, op, env)
            raise AppError(
                409,
                "close_conditions",
                "a conclusion is already recorded; it cannot be overwritten",
                item_no=item_no,
            )
        item["recorded_conclusion"] = incoming
        item["conclusion"] = req.conclusion
        self._touch_episode(rec)
        self._commit(rec)
        env = {"ok": True, "item_no": item_no, "state": item["state"], "recorded": True}
        return self._idem_put(idempotency_key, op, env)

    def _raise_close_blocked(self, item: dict[str, Any]) -> None:
        state = item.get("state")
        item_no = item.get("item_no")
        if state == "waiting_on_user":
            raise AppError(
                409,
                "waiting_on_user",
                "waiting_on_user items need a prior recorded user identity; this request cannot declare it",
                item_no=item_no,
            )
        raise AppError(
            409,
            "close_conditions",
            "close needs a prior recorded user identity plus a recorded conclusion and file_md5",
            item_no=item_no,
            state=state,
        )

    @staticmethod
    def _recorded_item_user(item: dict[str, Any]) -> bool:
        recorded = item.get("recorded_user")
        return isinstance(recorded, dict) and recorded.get("user") is True

    @staticmethod
    def _recorded_user_conclusion(item: dict[str, Any]) -> bool:
        recorded = item.get("recorded_conclusion")
        return isinstance(recorded, dict) and recorded.get("user") is True and bool(recorded.get("conclusion"))

    def _require_close_conditions(self, rec: dict[str, Any], item: dict[str, Any], req: OpenItemCloseRequest) -> None:
        """Prior user identity + prior user conclusion + registered file_md5. Request claims are not identity."""
        recorded_user = item.get("recorded_user")
        if not self._recorded_item_user(item):
            self._raise_close_blocked(item)
        if req.actor != recorded_user.get("actor"):
            self._raise_close_blocked(item)
        recorded = item.get("recorded_conclusion")
        if not self._recorded_user_conclusion(item) or recorded.get("conclusion") != req.conclusion:
            self._raise_close_blocked(item)
        self._require_registered_md5(rec, req.file_md5, code="subject_mismatch")

    def close_open_item(
        self,
        project_id: str,
        ep: str,
        item_no: int,
        body: OpenItemCloseRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_biz(raw)
        reject_secret_fields(raw)
        req = body or OpenItemCloseRequest.model_validate(raw or {})
        op = f"open_item_close:{project_id}:{ep}:{item_no}:{req.conclusion}:{req.file_md5}"
        cached = self._idem_get(idempotency_key, op)
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        self._ensure_biz_fields(rec)
        item = rec["open_items"]["by_no"].get(str(item_no))
        if not item:
            raise AppError(404, "not_found", "open item not found", item_no=item_no)
        if item.get("state") == "closed":
            env = {"ok": True, "item_no": item_no, "state": "closed"}
            return self._idem_put(idempotency_key, op, env)
        self._require_close_conditions(rec, item, req)
        item["state"] = "closed"
        item["conclusion"] = req.conclusion
        item["file_md5"] = req.file_md5
        item["closed_by"] = req.actor
        item["closed_at"] = now_iso()
        self._touch_episode(rec)
        self._commit(rec)
        env = {"ok": True, "item_no": item_no, "state": "closed"}
        return self._idem_put(idempotency_key, op, env)

    # ----- 18 spend accumulator (one project cap) ----------------------------------

    def get_project_cost(self, project_id: str) -> dict[str, Any]:
        snap = self.cost_snapshot_project(project_id)
        return {"ok": True, **snap}

    def add_cost_entry(
        self,
        project_id: str,
        body: CostEntryRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_biz(raw)
        reject_secret_fields(raw)
        req = body or CostEntryRequest.model_validate(raw or {})
        op = f"cost_entry:{project_id}:{req.ref_id}"
        cached = self._idem_get(idempotency_key, op)
        if cached:
            return cached
        if req.episode_id:
            self._rec(project_id, validate_ep(req.episode_id))
        else:
            self._project(project_id)
        bucket = self._project_cost_bucket(project_id)
        existing = bucket["entries"].get(req.ref_id)
        if existing:
            snap = self.cost_snapshot_project(project_id)
            env = {"ok": True, **snap}
            return self._idem_put(idempotency_key, op, env)
        if req.amount < 0:
            raise AppError(422, "validation", "amount must be >= 0", field="amount")
        projected = float(bucket.get("spent") or 0.0) + float(req.amount)
        cap = float(bucket.get("cap") or SPEND_CAP)
        if projected > cap:
            raise AppError(
                409,
                "over_cap",
                "entry would exceed the project spend ceiling",
                spent=bucket.get("spent") or 0.0,
                cap=cap,
                amount=req.amount,
            )
        row = {
            "provider": req.provider,
            "operation": req.operation,
            "amount": float(req.amount),
            "currency": req.currency,
            "ref_id": req.ref_id,
            "actor": req.actor,
            "episode_id": req.episode_id,
            "recorded_at": now_iso(),
        }
        bucket["entries"][req.ref_id] = row
        bucket["order"].append(req.ref_id)
        bucket["spent"] = projected
        bucket["currency"] = req.currency
        proj = self._project(project_id)
        proj["updated_at"] = now_iso()
        self._save()
        snap = self.cost_snapshot_project(project_id)
        env = {"ok": True, **snap}
        return self._idem_put(idempotency_key, op, env)
