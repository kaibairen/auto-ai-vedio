from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from aiv_drama.errors import AppError
from aiv_drama.validate import now_iso, reject_force_keys, validate_ep
from aiv_drama_n4.gates import g3_locked
from aiv_drama_n4.projection import read_prompts_jsonl
from aiv_drama_post.models import (
    AudioBedRequest,
    AudioVoiceRequest,
    CostEntryRequest,
    OpenItemCloseRequest,
    OpenItemRequest,
    OutputRegisterRequest,
    ReviewRequest,
    RoughCutRequest,
    SeamMeasureRequest,
    SegmentVideoRequest,
    SubtitlePutRequest,
)
from aiv_drama_post.seams import load_ruleset, ruleset_md5
from aiv_drama_post.validate import is_user_conclusion
from aiv_schema.models import GATE_G3, NODE_DN3, NODE_DN4

COST_CAP_DEFAULT = 60.0
COST_CURRENCY_DEFAULT = "CNY"
VIDEO_KINDS = frozenset({"segment_video", "rough_cut"})


def _hex_md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _norm_md5(value: str) -> str:
    return (value or "").strip().lower()


def empty_cost() -> dict[str, Any]:
    return {
        "cap": COST_CAP_DEFAULT,
        "currency": COST_CURRENCY_DEFAULT,
        "entries": {},
        "redraw_failed": False,
    }


class DramaPostOps:
    """Outputs / video / reviews / cost. Does not write G1b/G2/G3 or accept ForcePass."""

    def _ensure_post_fields(self, rec: dict[str, Any]) -> None:
        rec.setdefault("look_attempt_ledger", {})
        rec.setdefault("outputs", [])
        rec.setdefault("output_counter", 0)
        rec.setdefault("rough_cuts", {})
        rec.setdefault("locked_video_stream_md5", None)
        rec.setdefault("seam_measurements", [])
        rec.setdefault("subtitles", {})
        rec.setdefault("audio_beds", {})
        rec.setdefault("audio_voices", {})
        rec.setdefault("reviews", [])
        rec.setdefault("review_counter", 0)
        rec.setdefault("open_items", [])
        rec.setdefault("segment_videos", {})
        rec.setdefault("episode_stopped", False)

    def _ensure_project_cost(self, project_id: str) -> dict[str, Any]:
        proj = self._project(project_id)
        if not isinstance(proj.get("cost"), dict):
            proj["cost"] = empty_cost()
        cost = proj["cost"]
        cost.setdefault("cap", COST_CAP_DEFAULT)
        cost.setdefault("currency", COST_CURRENCY_DEFAULT)
        cost.setdefault("entries", {})
        cost.setdefault("redraw_failed", False)
        return proj

    def _cost_snapshot(self, project_id: str) -> dict[str, Any]:
        proj = self._ensure_project_cost(project_id)
        cost = proj["cost"]
        spent = 0.0
        for entry in (cost.get("entries") or {}).values():
            if isinstance(entry, dict):
                spent += float(entry.get("amount") or 0)
        cap = float(cost.get("cap") or COST_CAP_DEFAULT)
        remaining = round(cap - spent, 6)
        if remaining < 0:
            remaining = 0.0
        return {
            "spent": round(spent, 6),
            "cap": cap,
            "remaining": remaining,
            "blocked": remaining <= 0,
        }

    def require_generation_open(self, project_id: str) -> dict[str, Any]:
        view = self._cost_snapshot(project_id)
        if view["blocked"]:
            raise AppError(
                409,
                "over_cap",
                "cost cap reached; provider call blocked",
                spent=view["spent"],
                cap=view["cap"],
                remaining=view["remaining"],
                blocked=True,
            )
        return view

    def require_redraw_consent(self, project_id: str, raw: dict[str, Any] | None) -> None:
        incoming = raw if isinstance(raw, dict) else {}
        proj = self._ensure_project_cost(project_id)
        if not proj["cost"].get("redraw_failed"):
            return
        if incoming.get("user_consent") is True:
            return
        raise AppError(
            409,
            "redraw_needs_user",
            "a prior redraw failed; explicit user consent is required",
            redraw_failed=True,
        )

    def mark_redraw_outcome(self, project_id: str, *, ok: bool) -> None:
        proj = self._ensure_project_cost(project_id)
        proj["cost"]["redraw_failed"] = not ok
        self._save()

    def get_cost(self, project_id: str) -> dict[str, Any]:
        self._project(project_id)
        return self._cost_snapshot(project_id)

    def add_cost_entry(
        self,
        project_id: str,
        body: CostEntryRequest,
        *,
        raw: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reject_force_keys(raw)
        self._require_active_project(project_id)
        proj = self._ensure_project_cost(project_id)
        entries = proj["cost"].setdefault("entries", {})
        existing = entries.get(body.ref_id)
        if existing:
            return self._cost_snapshot(project_id)
        if body.amount < 0:
            raise AppError(422, "validation", "amount must be >= 0", field="amount")
        view = self._cost_snapshot(project_id)
        if view["spent"] + float(body.amount) > view["cap"]:
            raise AppError(
                409,
                "over_cap",
                "entry would exceed cost cap; not written",
                spent=view["spent"],
                cap=view["cap"],
                remaining=view["remaining"],
                blocked=view["blocked"],
                amount=body.amount,
            )
        entries[body.ref_id] = {
            "provider": body.provider,
            "operation": body.operation,
            "amount": float(body.amount),
            "currency": body.currency,
            "ref_id": body.ref_id,
            "actor": body.actor,
            "at": now_iso(),
        }
        self._save()
        return self._cost_snapshot(project_id)

    def _resolve_existing_file(self, path_str: str) -> Path:
        raw = Path(path_str)
        candidates = [raw]
        if not raw.is_absolute():
            candidates.append(self.settings.data_dir / raw)
        for cand in candidates:
            if cand.is_file():
                return cand
        raise AppError(400, "validation", "output path does not exist", path=path_str)

    def _find_output(self, rec: dict[str, Any], md5: str) -> dict[str, Any] | None:
        digest = _norm_md5(md5)
        for item in rec.get("outputs") or []:
            if isinstance(item, dict) and _norm_md5(str(item.get("md5") or "")) == digest:
                return item
        return None

    def register_output(
        self,
        project_id: str,
        ep: str,
        body: OutputRegisterRequest,
        *,
        raw: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reject_force_keys(raw)
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        path = self._resolve_existing_file(body.path)
        actual = _hex_md5(path.read_bytes())
        if actual != _norm_md5(body.md5):
            raise AppError(
                409,
                "md5_mismatch",
                "server md5 does not match request",
                expected=body.md5,
                actual=actual,
            )
        size = path.stat().st_size
        if int(body.bytes) != int(size):
            raise AppError(400, "validation", "bytes does not match file size", field="bytes")
        existing = self._find_output(rec, actual)
        if existing:
            return {
                "output_id": existing["output_id"],
                "md5": existing["md5"],
                "registered_at": existing["registered_at"],
            }
        rec["output_counter"] = int(rec.get("output_counter") or 0) + 1
        output_id = f"out_{rec['output_counter']:04d}"
        ts = now_iso()
        rec.setdefault("outputs", []).append(
            {
                "output_id": output_id,
                "kind": body.kind,
                "path": str(path),
                "md5": actual,
                "bytes": int(size),
                "parent_md5": body.parent_md5,
                "actor": body.actor,
                "registered_at": ts,
            }
        )
        self._touch_episode(rec)
        self._commit(rec)
        return {"output_id": output_id, "md5": actual, "registered_at": ts}

    def _assembled_lines(self, rec: dict[str, Any]) -> list[dict[str, Any]]:
        n4 = rec.get("n4") or {}
        if not n4.get("started"):
            return []
        episode_dir = self.store.episode_dir(rec["episode"]["project_id"], rec["episode"]["episode_id"])
        return read_prompts_jsonl(episode_dir, rec["episode"]["episode_id"])

    def _line_shas(self, line: dict[str, Any]) -> set[str]:
        prompt = line.get("prompt") or ""
        out = {hashlib.sha256(prompt.encode("utf-8")).hexdigest()}
        fp = line.get("fingerprint")
        if isinstance(fp, str) and fp:
            out.add(fp)
        return out

    def _require_video_upstream(self, rec: dict[str, Any]) -> None:
        if not g3_locked(rec):
            raise AppError(
                409,
                "upstream_unlocked",
                "G3 unlocked or N4 not assembled",
                gate=GATE_G3,
                node=NODE_DN3,
            )
        n4 = rec.get("n4") or {}
        if not n4.get("started"):
            raise AppError(
                409,
                "upstream_unlocked",
                "N4 not assembled; cannot request segment video",
                node=NODE_DN4,
            )

    def _run_seedance(
        self,
        *,
        rec: dict[str, Any],
        segment_id: str,
        prompt_sha256: str,
    ) -> dict[str, Any]:
        hook = getattr(self, "seedance_hook", None)
        if callable(hook):
            return hook(segment_id=segment_id, prompt_sha256=prompt_sha256, rec=rec)
        dest = self.store.episode_dir(rec["episode"]["project_id"], rec["episode"]["episode_id"])
        dest = dest / "segments"
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"{segment_id}.bin"
        payload = f"seedance-fixture:{segment_id}:{prompt_sha256}".encode("utf-8")
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(payload)
        tmp.replace(path)
        return {
            "status": "succeeded",
            "output_md5": _hex_md5(payload),
            "output_path": str(path),
            "provider_request_id": f"fixture-{segment_id}",
        }

    def generate_segment_video(
        self,
        project_id: str,
        ep: str,
        segment_id: str,
        body: SegmentVideoRequest,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys(raw)
        incoming = raw if isinstance(raw, dict) else {}
        cached = self._idem_get(idempotency_key, f"segment_video:{project_id}:{ep}:{segment_id}")
        if cached:
            return cached
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        self._require_video_upstream(rec)
        ledger = rec.setdefault("segment_videos", {})
        prior = ledger.get(segment_id)
        if prior:
            raise AppError(
                409,
                "already_attempted",
                "this segment already used its one attempt",
                segment_id=segment_id,
                attempt=1,
            )
        if rec.get("episode_stopped"):
            raise AppError(
                409,
                "episode_stopped",
                "a prior segment failed; episode is stopped",
                segment_id=segment_id,
            )
        lines = self._assembled_lines(rec)
        line = next((row for row in lines if row.get("shot_id") == segment_id), None)
        if line is None:
            raise AppError(
                409,
                "prompt_mismatch",
                "segment_id is not an assembled shot",
                segment_id=segment_id,
            )
        if _norm_md5(body.prompt_sha256) not in {_norm_md5(s) for s in self._line_shas(line)}:
            raise AppError(
                409,
                "prompt_mismatch",
                "prompt_sha256 does not match assembled line",
                segment_id=segment_id,
            )
        self.require_generation_open(project_id)
        self.require_redraw_consent(project_id, incoming)
        try:
            result = self._run_seedance(rec=rec, segment_id=segment_id, prompt_sha256=body.prompt_sha256)
        except AppError as exc:
            record = {
                "segment_id": segment_id,
                "status": "failed",
                "attempt": 1,
                "output_md5": None,
                "output_path": None,
                "provider_request_id": None,
                "prompt_sha256": body.prompt_sha256,
                "ref_md5s": list(body.ref_md5s),
                "tool_profile": body.tool_profile,
                "actor": body.actor,
                "at": now_iso(),
            }
            ledger[segment_id] = record
            rec["episode_stopped"] = True
            self.mark_redraw_outcome(project_id, ok=False)
            self._touch_episode(rec)
            self._commit(rec)
            if exc.status_code == 502 and exc.code == "provider":
                raise
            raise AppError(502, "provider", str(exc), segment_id=segment_id) from exc
        status = result.get("status") or "failed"
        record = {
            "segment_id": segment_id,
            "status": status,
            "attempt": 1,
            "output_md5": result.get("output_md5"),
            "output_path": result.get("output_path"),
            "provider_request_id": result.get("provider_request_id"),
            "prompt_sha256": body.prompt_sha256,
            "ref_md5s": list(body.ref_md5s),
            "tool_profile": body.tool_profile,
            "actor": body.actor,
            "at": now_iso(),
        }
        ledger[segment_id] = record
        if status != "succeeded":
            rec["episode_stopped"] = True
            self.mark_redraw_outcome(project_id, ok=False)
        else:
            self.mark_redraw_outcome(project_id, ok=True)
        self._touch_episode(rec)
        self._commit(rec)
        body_out = {
            "segment_id": segment_id,
            "status": record["status"],
            "attempt": 1,
            "output_md5": record["output_md5"],
            "output_path": record["output_path"],
            "provider_request_id": record["provider_request_id"],
        }
        return self._idem_put(idempotency_key, f"segment_video:{project_id}:{ep}:{segment_id}", body_out)

    def create_rough_cut(
        self,
        project_id: str,
        ep: str,
        body: RoughCutRequest,
        *,
        raw: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reject_force_keys(raw)
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        cuts = rec.setdefault("rough_cuts", {})
        existing = cuts.get(body.version)
        payload_md5s = {
            "video_stream_md5": _norm_md5(body.video_stream_md5),
            "audio_md5": _norm_md5(body.audio_md5),
            "subtitle_md5": _norm_md5(body.subtitle_md5) if body.subtitle_md5 else None,
        }
        if existing:
            same = (
                existing.get("video_stream_md5") == payload_md5s["video_stream_md5"]
                and existing.get("audio_md5") == payload_md5s["audio_md5"]
                and (existing.get("subtitle_md5") or None) == payload_md5s["subtitle_md5"]
            )
            if same:
                return {
                    "version": existing["version"],
                    "output_md5": existing["output_md5"],
                    "video_stream_md5": existing["video_stream_md5"],
                    "framemd5": existing["framemd5"],
                }
            raise AppError(409, "version_exists", "rough-cut version already exists", version=body.version)
        locked = rec.get("locked_video_stream_md5")
        stream = payload_md5s["video_stream_md5"]
        source = self._find_output(rec, stream)
        if locked and locked != stream:
            raise AppError(
                409,
                "video_stream_mismatch",
                "video stream md5 changed; cut not written",
                expected=locked,
                actual=stream,
            )
        if not source or source.get("kind") not in VIDEO_KINDS:
            raise AppError(
                409,
                "video_stream_mismatch",
                "video_stream_md5 is not the locked / registered video stream",
                video_stream_md5=stream,
            )
        if locked is None:
            rec["locked_video_stream_md5"] = stream
        output_md5 = _hex_md5(
            f"{body.version}:{stream}:{payload_md5s['audio_md5']}:{payload_md5s['subtitle_md5'] or ''}".encode("utf-8")
        )
        framemd5 = _hex_md5(f"framemd5:{stream}:{body.version}".encode("utf-8"))
        record = {
            "version": body.version,
            "video_stream_md5": stream,
            "audio_md5": payload_md5s["audio_md5"],
            "subtitle_md5": payload_md5s["subtitle_md5"],
            "parent_version": body.parent_version,
            "output_md5": output_md5,
            "framemd5": framemd5,
            "actor": body.actor,
            "at": now_iso(),
        }
        cuts[body.version] = record
        self._touch_episode(rec)
        self._commit(rec)
        return {
            "version": body.version,
            "output_md5": output_md5,
            "video_stream_md5": stream,
            "framemd5": framemd5,
        }

    def measure_seams(
        self,
        project_id: str,
        ep: str,
        version: str,
        body: SeamMeasureRequest,
        *,
        raw: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reject_force_keys(raw)
        rec = self._rec(project_id, validate_ep(ep))
        cut = (rec.get("rough_cuts") or {}).get(version)
        if not cut:
            raise AppError(404, "not_found", "rough-cut version not found", version=version)
        expected = ruleset_md5()
        if _norm_md5(body.ruleset_md5) != expected:
            raise AppError(
                409,
                "ruleset_mismatch",
                "ruleset_md5 does not match the measurement ruleset",
                expected=expected,
            )
        key = f"{version}:{expected}"
        for prior in rec.get("seam_measurements") or []:
            if prior.get("key") == key:
                return {
                    "version": version,
                    "pass": prior["pass"],
                    "seams": deepcopy(prior["seams"]),
                }
        rules = load_ruleset()
        metrics = rules.get("metrics") or {}
        seams = [
            {
                "at_s": 0.0,
                "metric": name,
                "value": 0.0,
                "limit": float(limit),
                "pass": 0.0 <= float(limit),
            }
            for name, limit in metrics.items()
        ]
        passed = all(item["pass"] for item in seams)
        rec.setdefault("seam_measurements", []).append(
            {
                "key": key,
                "version": version,
                "ruleset_md5": expected,
                "pass": passed,
                "seams": seams,
                "actor": body.actor,
                "at": now_iso(),
            }
        )
        self._touch_episode(rec)
        self._commit(rec)
        return {"version": version, "pass": passed, "seams": seams}

    def put_subtitles(
        self,
        project_id: str,
        ep: str,
        version: str,
        body: SubtitlePutRequest,
        *,
        raw: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reject_force_keys(raw)
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        for point in body.in_points:
            if point.in_s >= point.out_s:
                raise AppError(400, "validation", "in_s must be earlier than out_s", field="in_points")
        existing = (rec.get("subtitles") or {}).get(version)
        sha = _norm_md5(body.body_sha256)
        if existing:
            if _norm_md5(existing.get("body_sha256") or "") == sha:
                return {
                    "version": existing["version"],
                    "body_sha256": existing["body_sha256"],
                    "line_count": existing["line_count"],
                }
            raise AppError(409, "version_exists", "subtitle version already exists", version=version)
        burned = [
            cut
            for cut in (rec.get("rough_cuts") or {}).values()
            if cut.get("subtitle_md5") and _norm_md5(cut["subtitle_md5"]) == sha
        ]
        record = {
            "version": version,
            "body_sha256": sha,
            "line_count": len(body.in_points),
            "in_points": [p.model_dump() for p in body.in_points],
            "actor": body.actor,
            "at": now_iso(),
            "burned": bool(burned),
        }
        rec.setdefault("subtitles", {})[version] = record
        self._touch_episode(rec)
        self._commit(rec)
        return {"version": version, "body_sha256": sha, "line_count": record["line_count"]}

    def create_audio_bed(
        self,
        project_id: str,
        ep: str,
        body: AudioBedRequest,
        *,
        raw: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reject_force_keys(raw)
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        for src in body.sources:
            if not self._find_output(rec, src.md5):
                raise AppError(
                    422,
                    "source_unregistered",
                    "audio source md5 is not registered",
                    source_id=src.source_id,
                    md5=src.md5,
                )
        material = {
            "version": body.version,
            "spec_md5": _norm_md5(body.spec_md5),
            "sources": [s.model_dump() for s in body.sources],
        }
        bed_md5 = _hex_md5(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        existing = (rec.get("audio_beds") or {}).get(body.version)
        if existing:
            if existing.get("bed_md5") == bed_md5:
                return {
                    "version": existing["version"],
                    "bed_md5": existing["bed_md5"],
                    "sample_rate": existing["sample_rate"],
                    "channels": existing["channels"],
                }
            raise AppError(409, "version_exists", "audio bed version already exists", version=body.version)
        record = {
            "version": body.version,
            "bed_md5": bed_md5,
            "sample_rate": 48000,
            "channels": 2,
            "spec_md5": material["spec_md5"],
            "sources": material["sources"],
            "actor": body.actor,
            "at": now_iso(),
        }
        rec.setdefault("audio_beds", {})[body.version] = record
        self._touch_episode(rec)
        self._commit(rec)
        return {
            "version": body.version,
            "bed_md5": bed_md5,
            "sample_rate": 48000,
            "channels": 2,
        }

    def place_audio_voice(
        self,
        project_id: str,
        ep: str,
        body: AudioVoiceRequest,
        *,
        raw: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reject_force_keys(raw)
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        take = self._find_output(rec, body.take_md5)
        if not take or take.get("kind") != "tts_line":
            raise AppError(409, "take_unregistered", "take_md5 is not a registered tts_line", take_md5=body.take_md5)
        key = f"{body.version}:{body.line_no}:{_norm_md5(body.take_md5)}"
        existing = (rec.get("audio_voices") or {}).get(key)
        if existing:
            return {
                "version": existing["version"],
                "line_no": existing["line_no"],
                "placed_md5": existing["placed_md5"],
            }
        version_hit = next(
            (
                row
                for row in (rec.get("audio_voices") or {}).values()
                if row.get("version") == body.version and row.get("line_no") == body.line_no
                and _norm_md5(row.get("take_md5") or "") != _norm_md5(body.take_md5)
            ),
            None,
        )
        if version_hit:
            raise AppError(409, "version_exists", "voice version+line already placed", version=body.version)
        placed = _hex_md5(f"{body.version}:{body.line_no}:{_norm_md5(body.take_md5)}:{body.in_s}".encode("utf-8"))
        record = {
            "version": body.version,
            "line_no": body.line_no,
            "take_md5": _norm_md5(body.take_md5),
            "in_s": body.in_s,
            "placed_md5": placed,
            "actor": body.actor,
            "at": now_iso(),
        }
        rec.setdefault("audio_voices", {})[key] = record
        self._touch_episode(rec)
        self._commit(rec)
        return {"version": body.version, "line_no": body.line_no, "placed_md5": placed}

    def create_review(
        self,
        project_id: str,
        ep: str,
        body: ReviewRequest,
        *,
        raw: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reject_force_keys(raw)
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        subject = self._find_output(rec, body.subject_md5)
        if not subject:
            raise AppError(
                409,
                "subject_mismatch",
                "subject_md5 is not a registered output",
                subject_md5=body.subject_md5,
            )
        for prior in rec.get("reviews") or []:
            if (
                prior.get("level") == body.level
                and _norm_md5(prior.get("subject_md5") or "") == _norm_md5(body.subject_md5)
                and prior.get("actor") == body.actor
            ):
                return {"review_id": prior["review_id"], "state": prior["state"]}
        if body.level == "L2" and body.verdict == "pass":
            blocking = [
                item
                for item in rec.get("open_items") or []
                if item.get("state") == "blocks_l2"
            ]
            if blocking:
                raise AppError(
                    409,
                    "blocks_l2_open",
                    "blocking open items remain; L2 cannot pass",
                    item_nos=[item.get("item_no") for item in blocking],
                )
        rec["review_counter"] = int(rec.get("review_counter") or 0) + 1
        review_id = f"rev_{rec['review_counter']:04d}"
        record = {
            "review_id": review_id,
            "level": body.level,
            "subject_md5": _norm_md5(body.subject_md5),
            "verdict": body.verdict,
            "state": body.verdict,
            "actor": body.actor,
            "at": now_iso(),
        }
        rec.setdefault("reviews", []).append(record)
        self._touch_episode(rec)
        self._commit(rec)
        return {"review_id": review_id, "state": record["state"]}

    def create_open_item(
        self,
        project_id: str,
        ep: str,
        body: OpenItemRequest,
        *,
        raw: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reject_force_keys(raw)
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        reviews = {row.get("review_id"): row for row in rec.get("reviews") or []}
        if body.review_id not in reviews:
            raise AppError(400, "validation", "review_id not found", field="review_id")
        for item in rec.get("open_items") or []:
            if item.get("review_id") == body.review_id and item.get("item_no") == body.item_no:
                return {"item_no": item["item_no"], "state": item["state"]}
        record = {
            "review_id": body.review_id,
            "item_no": body.item_no,
            "state": body.state,
            "owner": body.owner,
            "text": body.text,
            "conclusion": None,
            "file_md5": None,
            "at": now_iso(),
        }
        rec.setdefault("open_items", []).append(record)
        self._touch_episode(rec)
        self._commit(rec)
        return {"item_no": body.item_no, "state": body.state}

    def close_open_item(
        self,
        project_id: str,
        ep: str,
        item_no: int,
        body: OpenItemCloseRequest,
        *,
        raw: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reject_force_keys(raw)
        rec = self._rec(project_id, validate_ep(ep))
        self._require_writable_episode(rec)
        item = next((row for row in rec.get("open_items") or [] if row.get("item_no") == item_no), None)
        if not item:
            raise AppError(404, "not_found", "open item not found", item_no=item_no)
        incoming = raw if isinstance(raw, dict) else {}
        if "evidence_md5" in incoming and "file_md5" not in incoming:
            raise AppError(400, "validation", "file_md5 is required; evidence_md5 is not enough", field="file_md5")
        if item.get("state") == "waiting_on_user" and not is_user_conclusion(body.conclusion):
            raise AppError(
                409,
                "waiting_on_user",
                "waiting_on_user items need a user conclusion (user:...) plus file_md5",
                item_no=item_no,
            )
        if not self._find_output(rec, body.file_md5):
            raise AppError(409, "subject_mismatch", "file_md5 is not a registered output", file_md5=body.file_md5)
        item["state"] = "closed"
        item["conclusion"] = body.conclusion
        item["file_md5"] = _norm_md5(body.file_md5)
        item["closed_by"] = body.actor
        item["closed_at"] = now_iso()
        self._touch_episode(rec)
        self._commit(rec)
        return {"item_no": item_no, "state": "closed"}
