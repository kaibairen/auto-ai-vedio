from __future__ import annotations

from copy import deepcopy
from typing import Any

from aiv_drama.errors import AppError
from aiv_drama.validate import now_iso
from aiv_drama_n3.ops import DramaN3Ops
from aiv_drama_n4.assemble import assemble_episode_lines, assemble_fingerprint, card_fingerprint, g2_fingerprint
from aiv_drama_n3.char_look import char_look_envelope_fields
from aiv_drama_n3.scene_look import resolve_scene_look_policy, scene_look_envelope_fields
from aiv_drama_n4.gates import (
    episode_ready_for_n4,
    episode_usable_for_n4,
    require_assemble_gates,
    require_g3_for_n4_read,
)
from aiv_drama_n4.models import N4AssembleRequest, N4ValidateRequest
from aiv_drama_n4.projection import (
    prompts_jsonl_relpath,
    prompts_jsonl_versioned_relpath,
    read_prompts_jsonl,
    write_prompts_jsonl,
)
from aiv_drama_n4.skeleton import SKELETON_ID, SKELETON_VERSION
from aiv_drama_n4.tools import adapter_observability, lookup_adapter, normalize_tool_profile
from aiv_drama_n4.validate import (
    collect_n4_issues,
    collect_scene_missing_refs,
    first_shot_review,
    raise_hard_n4,
    reject_force_keys_n4,
)
from aiv_schema.models import GATE_G3, NODE_DN3, NODE_DN4, PIPELINE_DRAMA


def empty_n4(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "episode_id": rec["episode"]["episode_id"],
        "pipeline_profile": PIPELINE_DRAMA,
        "started": False,
        "stale": False,
        "assemble_version": 0,
        "previous_assemble_version": None,
        "fingerprint": None,
        "g2_fingerprint": None,
        "tool_profile": None,
        "tool_profile_input": None,
        "aspect": None,
        "artifact": None,
        "artifact_versioned": None,
        "shot_count": 0,
        "history": [],
        "upstream_cards_version": ((rec.get("n3") or {}).get("cards") or {}).get("version") or 0,
        "upstream_storyboard_version": (rec.get("storyboard") or {}).get("version") or 0,
        "upstream_cast_version": (rec.get("cast") or {}).get("version") or 0,
        "assembled_at": None,
        "assembled_by": None,
        "skeleton_id": SKELETON_ID,
        "skeleton_version": SKELETON_VERSION,
    }


class DramaN4Ops(DramaN3Ops):
    """D-N4 deterministic assemble. Does not live in drama-n3-core."""

    def _ensure_n4_fields(self, rec: dict[str, Any]) -> None:
        rec["episode"]["versions"].setdefault("prompts", 0)
        rec.setdefault("d_n4_jobs", [])
        if rec.get("n4") is None:
            rec["n4"] = None
        self._refresh_n4_stale(rec)

    def _stale_n3(self, rec: dict[str, Any]) -> None:
        super()._stale_n3(rec)
        self._stale_n4(rec)

    def _stale_n4(self, rec: dict[str, Any]) -> None:
        n4 = rec.get("n4")
        if not n4:
            return
        n4["stale"] = True
        if NODE_DN4 not in (rec["episode"].get("stale_downstream") or []):
            rec["episode"].setdefault("stale_downstream", []).append(NODE_DN4)

    def _refresh_n4_stale(self, rec: dict[str, Any]) -> None:
        n4 = rec.get("n4")
        if not n4:
            return
        cards_ver = ((rec.get("n3") or {}).get("cards") or {}).get("version") or 0
        sb_ver = (rec.get("storyboard") or {}).get("version") or 0
        cast_ver = (rec.get("cast") or {}).get("version") or 0
        cards_stale = bool(((rec.get("n3") or {}).get("cards") or {}).get("stale"))
        if (
            cards_stale
            or cards_ver != n4.get("upstream_cards_version")
            or sb_ver != n4.get("upstream_storyboard_version")
            or cast_ver != n4.get("upstream_cast_version")
        ):
            self._stale_n4(rec)

    def _n4_aspect(self, rec: dict[str, Any], requested: str | None) -> str:
        raw = (requested or rec["episode"].get("aspect_ratio") or "9:16").strip() or "9:16"
        adapter = lookup_adapter("seedance_2")
        if adapter and raw not in adapter.allowed_aspects:
            raise AppError(
                422,
                "validation_failed",
                "aspect 须为 9:16 / 16:9 / 2.35:1",
                node=NODE_DN4,
                aspect=raw,
            )
        return raw

    def _n4_lines_from_disk(self, rec: dict[str, Any]) -> list[dict[str, Any]]:
        ep = rec["episode"]["episode_id"]
        episode_dir = self.store.episode_dir(rec["episode"]["project_id"], ep)
        return read_prompts_jsonl(episode_dir, ep)

    def n4_envelope(
        self,
        rec: dict[str, Any],
        *,
        warnings: list[dict[str, Any]] | None = None,
        extra: dict[str, Any] | None = None,
        lines: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        n4 = deepcopy(rec.get("n4") or empty_n4(rec))
        usable, missing = episode_usable_for_n4(rec, self.settings)
        ready = episode_ready_for_n4(rec)
        policy = resolve_scene_look_policy(rec)
        scene_missing = collect_scene_missing_refs(rec.get("n3"), self.settings) if policy.scene_optional else []
        artifact = n4.get("artifact")
        env: dict[str, Any] = {
            "ok": True,
            "project_id": rec["episode"]["project_id"],
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN4,
            "n4": n4,
            "started": bool(n4.get("started")),
            "stale": bool(n4.get("stale")),
            "assemble_version": n4.get("assemble_version") or 0,
            "fingerprint": n4.get("fingerprint"),
            "g2_fingerprint": n4.get("g2_fingerprint") or g2_fingerprint(rec),
            "tool_profile": n4.get("tool_profile"),
            "artifact": artifact,
            "path": artifact,
            "usable_for_n4": usable,
            "ready_for_n4": ready,
            "missing_refs": missing,
            "next_edges": list(rec["episode"].get("next_edges") or []),
            "stale_downstream": list(rec["episode"].get("stale_downstream") or []),
            "skeleton_id": SKELETON_ID,
            "skeleton_version": SKELETON_VERSION,
            "tool_adapters": adapter_observability(),
            "docs_pass": False,
            "auto_open_dn5": False,
        }
        env.update(scene_look_envelope_fields(policy, scene_missing_refs=scene_missing))
        env.update(char_look_envelope_fields(rec))
        if lines is not None:
            env["lines"] = lines
            env["shot_count"] = len(lines)
            env["first_shot_review"] = first_shot_review(lines)
            versions = {}
            for line in lines:
                versions.update(line.get("card_versions") or {})
            env["card_versions"] = versions
            env["card_fingerprint"] = card_fingerprint(versions) if versions else None
        elif n4.get("started"):
            env["shot_count"] = n4.get("shot_count") or 0
        if warnings:
            env["warnings"] = warnings
        if extra:
            env.update(extra)
        return env

    def get_n4(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, ep)
        require_g3_for_n4_read(rec)
        lines = self._n4_lines_from_disk(rec) if (rec.get("n4") or {}).get("started") else []
        issues = collect_n4_issues(rec, lines or None, settings=self.settings, for_write=False)
        warns = [i for i in issues if i.get("severity") == "warn"]
        extra = {"written": bool(lines)}
        if lines:
            extra["lines"] = lines
            extra["shot_count"] = len(lines)
            extra["first_shot_review"] = first_shot_review(lines)
        return self.n4_envelope(rec, warnings=warns or None, extra=extra, lines=lines or None)

    def get_n4_status(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, ep)
        require_g3_for_n4_read(rec)
        env = self.n4_envelope(rec)
        out: dict[str, Any] = {
            "ok": True,
            "project_id": env["project_id"],
            "episode_id": env["episode_id"],
            "node": NODE_DN4,
            "started": env["started"],
            "stale": env["stale"],
            "assemble_version": env["assemble_version"],
            "fingerprint": env["fingerprint"],
            "g2_fingerprint": env["g2_fingerprint"],
            "tool_profile": env["tool_profile"],
            "artifact": env["artifact"],
            "path": env.get("path"),
            "usable_for_n4": env["usable_for_n4"],
            "ready_for_n4": env["ready_for_n4"],
            "missing_refs": env["missing_refs"],
            "shot_count": (rec.get("n4") or {}).get("shot_count") or 0,
            "scene_look": env.get("scene_look"),
            "scene_look_source": env.get("scene_look_source"),
            "scene_look_scope": env.get("scene_look_scope"),
        }
        if "SCENE-LOOK-EXEMPT" in env:
            out["SCENE-LOOK-EXEMPT"] = env["SCENE-LOOK-EXEMPT"]
            out["scene_look_copy"] = env.get("scene_look_copy")
        if env.get("scene_missing_refs"):
            out["scene_missing_refs"] = env["scene_missing_refs"]
        return out

    def validate_n4(
        self,
        project_id: str,
        ep: str,
        body: N4ValidateRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_n4(raw)
        rec = self._rec(project_id, ep)
        require_g3_for_n4_read(rec)
        req = body or N4ValidateRequest()
        persist, original = normalize_tool_profile(
            req.tool_profile or (rec.get("storyboard") or {}).get("tool_profile")
        )
        aspect = self._n4_aspect(rec, req.aspect)
        preview = assemble_episode_lines(
            rec,
            tool_profile=persist,
            aspect=aspect,
            assemble_version=((rec.get("n4") or {}).get("assemble_version") or 0) + 1,
        )
        issues = collect_n4_issues(rec, preview, settings=self.settings, for_write=False)
        valid = all(i.get("severity") != "error" for i in issues)
        usable, missing = episode_usable_for_n4(rec, self.settings)
        policy = resolve_scene_look_policy(rec)
        scene_missing = collect_scene_missing_refs(rec.get("n3"), self.settings) if policy.scene_optional else []
        return {
            "ok": True,
            "project_id": project_id,
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN4,
            "valid": valid,
            "written": False,
            "usable_for_n4": usable,
            "ready_for_n4": episode_ready_for_n4(rec),
            "missing_refs": missing,
            **scene_look_envelope_fields(policy, scene_missing_refs=scene_missing),
            **char_look_envelope_fields(rec),
            "issues": issues,
            "warnings": [i for i in issues if i.get("severity") == "warn"],
            "tool_profile": persist,
            "tool_profile_input": original,
            "aspect": aspect,
            "shot_count": len(preview),
            "preview_shot_ids": [row.get("shot_id") for row in preview],
            "first_shot_review": first_shot_review(preview),
            "g2_fingerprint": g2_fingerprint(rec),
        }

    def assemble_n4(
        self,
        project_id: str,
        ep: str,
        body: N4AssembleRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_n4(raw)
        cached = self._idem_get(idempotency_key, f"n4_assemble:{project_id}:{ep}")
        if cached:
            return cached
        rec = self._rec(project_id, ep)
        self._require_writable_episode(rec)
        req = body or N4AssembleRequest()
        require_assemble_gates(rec, self.settings, force_reassemble=bool(req.force_reassemble))
        persist, original = normalize_tool_profile(
            req.tool_profile or (rec.get("storyboard") or {}).get("tool_profile")
        )
        aspect = self._n4_aspect(rec, req.aspect)
        cards = ((rec.get("n3") or {}).get("cards") or {})

        preview = assemble_episode_lines(rec, tool_profile=persist, aspect=aspect, assemble_version=0)
        issues = collect_n4_issues(rec, preview, settings=self.settings, for_write=True)
        raise_hard_n4(issues, extra={"written": False})

        prev = rec.get("n4") or empty_n4(rec)
        next_ver = int(prev.get("assemble_version") or 0) + 1
        lines = assemble_episode_lines(rec, tool_profile=persist, aspect=aspect, assemble_version=next_ver)
        g2_fp = g2_fingerprint(rec)
        fp = assemble_fingerprint(
            lines,
            meta={
                "assemble_version": next_ver,
                "cards_version": cards.get("version") or 0,
                "storyboard_version": (rec.get("storyboard") or {}).get("version") or 0,
                "cast_version": (rec.get("cast") or {}).get("version") or 0,
                "tool_profile": persist,
                "aspect": aspect,
                "g2_fingerprint": g2_fp,
            },
        )
        episode_dir = self.store.episode_dir(project_id, rec["episode"]["episode_id"])
        write_prompts_jsonl(episode_dir, rec["episode"]["episode_id"], lines, version=next_ver)
        rel = prompts_jsonl_relpath(rec["episode"]["episode_id"])
        rel_v = prompts_jsonl_versioned_relpath(rec["episode"]["episode_id"], next_ver)
        ts = now_iso()
        history = list(prev.get("history") or [])
        if prev.get("assemble_version"):
            history.append(
                {
                    "assemble_version": prev.get("assemble_version"),
                    "fingerprint": prev.get("fingerprint"),
                    "assembled_at": prev.get("assembled_at"),
                    "assembled_by": prev.get("assembled_by"),
                    "overwritten_at": ts,
                    "artifact_versioned": prev.get("artifact_versioned"),
                }
            )
        n4 = empty_n4(rec)
        n4.update(
            {
                "started": True,
                "stale": False,
                "assemble_version": next_ver,
                "previous_assemble_version": prev.get("assemble_version") or None,
                "fingerprint": fp,
                "g2_fingerprint": g2_fp,
                "tool_profile": persist,
                "tool_profile_input": original,
                "aspect": aspect,
                "artifact": rel,
                "artifact_versioned": rel_v,
                "shot_count": len(lines),
                "history": history[-10:],
                "upstream_cards_version": cards.get("version") or 0,
                "upstream_storyboard_version": (rec.get("storyboard") or {}).get("version") or 0,
                "upstream_cast_version": (rec.get("cast") or {}).get("version") or 0,
                "assembled_at": ts,
                "assembled_by": req.actor,
            }
        )
        rec["n4"] = n4
        rec["episode"]["versions"]["prompts"] = next_ver
        rec["episode"]["next_edges"] = [NODE_DN4]
        stale = rec["episode"].setdefault("stale_downstream", [])
        if NODE_DN4 in stale:
            stale.remove(NODE_DN4)
        rec["d_n4_jobs"] = [
            {
                "kind": "assemble",
                "assemble_version": next_ver,
                "artifact": rel,
                "artifact_versioned": rel_v,
                "fingerprint": fp,
                "g2_fingerprint": g2_fp,
                "tool_profile": persist,
                "at": ts,
                "actor": req.actor,
            }
        ]
        self._touch_episode(rec)
        self._commit(rec)
        warns = [i for i in collect_n4_issues(rec, lines, settings=self.settings, for_write=False) if i.get("severity") == "warn"]
        env = self.n4_envelope(
            rec,
            warnings=warns or None,
            extra={
                "written": True,
                "lines": lines,
                "shot_count": len(lines),
                "path": rel,
                "first_shot_review": first_shot_review(lines),
            },
            lines=lines,
        )
        return self._idem_put(idempotency_key, f"n4_assemble:{project_id}:{ep}", env)

    def get_dn4_consumer(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, ep)
        if not rec["gate_g3"].get("locked"):
            raise AppError(
                409,
                "upstream_unlocked",
                "D-N3 G3 未锁定；不可宣称可进 N4",
                node=NODE_DN3,
                gate=GATE_G3,
            )
        n4 = rec.get("n4") or {}
        started = bool(n4.get("started"))
        lines = self._n4_lines_from_disk(rec) if started else []
        usable, missing = episode_usable_for_n4(rec, self.settings)
        policy = resolve_scene_look_policy(rec)
        scene_missing = collect_scene_missing_refs(rec.get("n3"), self.settings) if policy.scene_optional else []
        return {
            "ok": True,
            "project_id": project_id,
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN3,
            "consumer": NODE_DN4,
            "started": started,
            "jobs": list(rec.get("d_n4_jobs") or []),
            "usable_for_n4": usable,
            "ready_for_n4": episode_ready_for_n4(rec),
            "missing_refs": missing,
            **scene_look_envelope_fields(policy, scene_missing_refs=scene_missing),
            **char_look_envelope_fields(rec),
            "stale": bool(n4.get("stale")),
            "assemble_version": n4.get("assemble_version") or 0,
            "fingerprint": n4.get("fingerprint"),
            "g2_fingerprint": n4.get("g2_fingerprint") or (g2_fingerprint(rec) if started else None),
            "artifact": n4.get("artifact"),
            "prompts_path": n4.get("artifact"),
            "path": n4.get("artifact"),
            "jsonl": lines,
            "shot_count": len(lines),
            "next_edges": list(rec["episode"].get("next_edges") or []),
            "note": (
                "assemble 已写 EP##-prompts.jsonl"
                if started
                else "G3 pass ≠ usable_for_n4；usable=true 且 ready_for_n4=true 后走 /drama/n4/assemble"
            ),
        }
