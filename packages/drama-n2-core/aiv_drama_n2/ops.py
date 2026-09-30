from __future__ import annotations

from copy import deepcopy
from typing import Any

from aiv_drama.errors import AppError
from aiv_drama.validate import check_if_match, now_iso
from aiv_drama_n2.models import (
    StoryboardGenerateRequest,
    StoryboardReorderRequest,
    StoryboardResetRequest,
    StoryboardWrite,
)
from aiv_drama_n2.named_cast import (
    AUTO_MERGE_ONE_LINE,
    G2_BLOCK_MESSAGE,
    NAMED_CAST_AUTO_MERGED,
    NAMED_CAST_GATE,
    auto_merge_named_cast,
    blocking_named_cast_issues,
    parse_named_cast_check,
)
from aiv_drama_n2.provider import generate_rows
from aiv_drama_n2.validate import (
    STORYBOARD_SKILL_PATH,
    collect_issues,
    inherit_shot_cap,
    issue,
    normalize_row,
    raise_hard,
    ready_for_n4,
    reject_force_keys_n2,
    reject_prompt_fields,
    reject_prompt_text,
)
from aiv_schema.models import GATE_G1B, GATE_G2, NODE_DN1, NODE_DN2, NODE_DN3, PIPELINE_DRAMA


def empty_gate_g2() -> dict[str, Any]:
    return {
        "gate_id": GATE_G2,
        "state": "idle",
        "locked": False,
        "version": 0,
        "last_decision": None,
        "note": None,
        "actor": None,
        "decided_at": None,
    }


class DramaN2Ops:
    """D-N2 storyboard + gate G2 methods mixed into DramaService."""

    def _ensure_n2_fields(self, rec: dict[str, Any]) -> None:
        rec["episode"]["versions"].setdefault("storyboard", 0)
        rec["episode"]["locks"].setdefault("g2", False)
        rec.setdefault("d_n3_jobs", [])
        rec.setdefault("storyboard", rec.get("storyboard"))
        if not rec.get("gate_g2"):
            rec["gate_g2"] = empty_gate_g2()

    def _mark_storyboard_stale(self, rec: dict[str, Any]) -> None:
        if rec.get("storyboard"):
            rec["storyboard"]["stale"] = True
            if rec["storyboard"].get("locked"):
                self._add_stale(rec, NODE_DN3)

    def _require_g1b_for_n2(self, rec: dict[str, Any]) -> None:
        outline = rec.get("outline") or {}
        cast = rec.get("cast") or {}
        gate = rec.get("gate") or {}
        locked = bool(outline.get("locked") and cast.get("locked") and gate.get("locked"))
        if not locked or gate.get("last_decision") != "pass":
            raise AppError(
                409,
                "upstream_unlocked",
                "D-N1 G1b not locked",
                node=NODE_DN1,
                gate=GATE_G1B,
            )
        if rec["episode"].get("pipeline_profile") != PIPELINE_DRAMA:
            raise AppError(422, "wrong_profile", "pipeline_profile must be drama", node=NODE_DN2)

    def _require_storyboard_unlock(self, rec: dict[str, Any], unlock_edit: bool) -> None:
        self._require_writable_episode(rec)
        sb = rec.get("storyboard") or {}
        if sb.get("locked"):
            if not unlock_edit:
                raise AppError(409, "locked", "locked; set unlock_edit to edit", node=NODE_DN2, gate=GATE_G2)
            sb["locked"] = False
            sb["confirmed_by"] = None
            rec["gate_g2"]["locked"] = False
            rec["gate_g2"]["state"] = "ready"
            rec["episode"]["locks"]["g2"] = False
            rec["episode"]["next_edges"] = [NODE_DN2]
            self._add_stale(rec, NODE_DN3)

    def _empty_storyboard(self, rec: dict[str, Any]) -> dict[str, Any]:
        outline = rec.get("outline") or {}
        cast = rec.get("cast") or {}
        cap = inherit_shot_cap(outline.get("shot_cap"))
        return {
            "episode_id": rec["episode"]["episode_id"],
            "pipeline_profile": PIPELINE_DRAMA,
            "lane": outline.get("lane") or cast.get("lane"),
            "shot_cap": cap,
            "shot_count": 0,
            "tool_profile": None,
            "storyboard_skill": "borrowed_dongman",
            "upstream_outline_version": outline.get("version") or 0,
            "upstream_cast_version": cast.get("version") or 0,
            "stale": False,
            "ready_for_n4": False,
            "rows": [],
            "version": 0,
            "locked": False,
            "confirmed_by": None,
            "updated_at": None,
            "updated_by": None,
            "job_id": None,
        }

    def _storyboard_view(self, rec: dict[str, Any]) -> dict[str, Any]:
        if rec.get("storyboard"):
            return deepcopy(rec["storyboard"])
        return self._empty_storyboard(rec)

    def _pin_upstream(self, rec: dict[str, Any], sb: dict[str, Any]) -> None:
        outline = rec.get("outline") or {}
        cast = rec.get("cast") or {}
        sb["upstream_outline_version"] = outline.get("version") or 0
        sb["upstream_cast_version"] = cast.get("version") or 0
        sb["lane"] = outline.get("lane") or cast.get("lane") or sb.get("lane")
        sb["stale"] = False

    def _named_cast_mode(self) -> str:
        return parse_named_cast_check(getattr(self.settings, "named_cast_check", None))

    def _collect_sb_issues(
        self,
        rec: dict[str, Any],
        rows: list[dict[str, Any]] | None = None,
        *,
        shot_cap: int | None = None,
        tool_profile: str | None = None,
        for_pass: bool = False,
    ) -> list[dict[str, Any]]:
        sb = rec.get("storyboard") or {}
        return collect_issues(
            rows if rows is not None else (sb.get("rows") or []),
            shot_cap=shot_cap if shot_cap is not None else (sb.get("shot_cap") or 12),
            tool_profile=tool_profile if tool_profile is not None else sb.get("tool_profile"),
            cast=rec.get("cast"),
            outline_body=(rec.get("outline") or {}).get("body_md"),
            for_pass=for_pass,
            named_cast_check=self._named_cast_mode(),
        )

    def _finish_storyboard(
        self,
        rec: dict[str, Any],
        sb: dict[str, Any],
        *,
        actor: str | None,
        bump: bool = True,
    ) -> None:
        issues = self._collect_sb_issues(rec, sb.get("rows") or [], shot_cap=sb.get("shot_cap") or 12)
        sb["ready_for_n4"] = ready_for_n4(sb.get("tool_profile"), issues)
        sb["shot_count"] = len(sb.get("rows") or [])
        if bump:
            sb["version"] = (sb.get("version") or 0) + 1
        sb["updated_at"] = now_iso()
        sb["updated_by"] = actor
        rec["storyboard"] = sb
        rec["gate_g2"]["state"] = "ready" if sb["shot_count"] else "idle"
        rec["gate_g2"]["locked"] = False
        rec["episode"]["locks"]["g2"] = False
        rec["episode"]["next_edges"] = [NODE_DN2]
        self._touch_episode(rec)

    def storyboard_envelope(self, rec: dict[str, Any], *, warnings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        sb = self._storyboard_view(rec)
        edges = list(rec["episode"].get("next_edges") or [])
        if sb.get("locked"):
            edges = [NODE_DN3]
        stale = list(rec["episode"].get("stale_downstream") or [])
        env: dict[str, Any] = {
            "ok": True,
            "project_id": rec["episode"]["project_id"],
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN2,
            "storyboard": sb,
            "next_edges": edges,
            "stale_downstream": stale,
        }
        if rec.get("projection_dirty"):
            env["projection_dirty"] = True
        if warnings:
            env["validate_warnings"] = warnings
        skill_paths = [p for p in (sb.get("skill_paths") or []) if p and p != "none"]
        src = rec.get("source_storyboard_skill")
        if src and src not in skill_paths:
            skill_paths.append(src)
        env["skill_paths"] = skill_paths
        env["storyboard_skill"] = sb.get("storyboard_skill")
        hint_fn = getattr(self, "_hint_fields", None)
        if callable(hint_fn):
            env.update(hint_fn(rec))
        return env

    def gate_g2_envelope(self, rec: dict[str, Any]) -> dict[str, Any]:
        sb = deepcopy(rec["storyboard"]) if rec.get("storyboard") else None
        edges = list(rec["episode"].get("next_edges") or [])
        if sb and sb.get("locked"):
            edges = [NODE_DN3]
        return {
            "ok": True,
            "project_id": rec["episode"]["project_id"],
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN2,
            "gate": deepcopy(rec["gate_g2"]),
            "storyboard": sb,
            "next_edges": edges,
        }

    def _storyboard_rows_from_write(self, rows: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for i, row in enumerate(rows, start=1):
            payload = row.model_dump() if hasattr(row, "model_dump") else dict(row)
            reject_prompt_text(shot_id=payload.get("shot_id"), field="action", value=payload.get("action"))
            reject_prompt_text(shot_id=payload.get("shot_id"), field="dialogue", value=payload.get("dialogue"))
            reject_prompt_text(shot_id=payload.get("shot_id"), field="notes", value=payload.get("notes"))
            out.append(normalize_row(payload, index=i))
        return out

    def get_storyboard(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, ep)
        self._require_g1b_for_n2(rec)
        issues = self._collect_sb_issues(
            rec,
            (rec.get("storyboard") or {}).get("rows") or [],
            shot_cap=(rec.get("storyboard") or self._empty_storyboard(rec)).get("shot_cap") or 12,
        )
        warns = [i for i in issues if i.get("severity") == "warn"]
        return self.storyboard_envelope(rec, warnings=warns or None)

    def put_storyboard(
        self,
        project_id: str,
        ep: str,
        body: StoryboardWrite,
        *,
        raw: dict[str, Any] | None = None,
        if_match: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_n2(raw)
        reject_prompt_fields(raw)
        cached = self._idem_get(idempotency_key, f"put_storyboard:{project_id}:{ep}")
        if cached:
            return cached
        rec = self._rec(project_id, ep)
        self._require_g1b_for_n2(rec)
        sb = rec.get("storyboard") or self._empty_storyboard(rec)
        check_if_match(if_match, sb.get("version") or 0, "storyboard")
        self._require_storyboard_unlock(rec, body.unlock_edit)
        if not body.rows:
            raise AppError(
                422,
                "shot_cap_exceeded",
                "rows exceed shot_cap",
                shot_cap=sb.get("shot_cap") or 12,
                row_count=0,
                node=NODE_DN2,
            )
        rows = self._storyboard_rows_from_write(body.rows)
        cap = inherit_shot_cap((rec.get("outline") or {}).get("shot_cap") or sb.get("shot_cap"))
        if body.tool_profile is not None:
            sb["tool_profile"] = body.tool_profile
        if body.storyboard_skill:
            sb["storyboard_skill"] = body.storyboard_skill
        sb["shot_cap"] = cap
        sb["rows"] = rows
        sb["shot_count"] = len(rows)
        issues = self._collect_sb_issues(rec, rows, shot_cap=cap, tool_profile=sb.get("tool_profile"))
        raise_hard(issues)
        self._pin_upstream(rec, sb)
        sb["locked"] = False
        sb["confirmed_by"] = None
        self._finish_storyboard(rec, sb, actor=body.actor)
        self._commit(rec)
        warns = [i for i in issues if i.get("severity") == "warn"]
        return self._idem_put(
            idempotency_key,
            f"put_storyboard:{project_id}:{ep}",
            self.storyboard_envelope(rec, warnings=warns or None),
        )

    def generate_storyboard(
        self,
        project_id: str,
        ep: str,
        body: StoryboardGenerateRequest | None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        incoming = raw if isinstance(raw, dict) else {}
        reject_force_keys_n2(incoming)
        reject_prompt_fields(incoming)
        cached = self._idem_get(idempotency_key, f"generate_storyboard:{project_id}:{ep}")
        if cached:
            return cached
        rec = self._rec(project_id, ep)
        self._require_g1b_for_n2(rec)
        req = body or StoryboardGenerateRequest()
        sb = rec.get("storyboard") or self._empty_storyboard(rec)
        self._require_storyboard_unlock(rec, req.unlock_edit)
        cap = inherit_shot_cap((rec.get("outline") or {}).get("shot_cap"), req.shot_cap_override)
        skill = req.storyboard_skill or "borrowed_dongman"
        if skill == "borrowed_dongman":
            skill_path = self.settings.repo_root / STORYBOARD_SKILL_PATH
            if not skill_path.is_file():
                raise AppError(
                    422,
                    "provider",
                    "borrowed_dongman skill missing (read-only path)",
                    path=STORYBOARD_SKILL_PATH,
                )
        rows = generate_rows(
            self.settings,
            provider=req.provider,
            outline=rec.get("outline") or {},
            cast=rec.get("cast") or {},
            shot_cap=cap,
            tool_profile=req.tool_profile,
            episode_id=rec["episode"]["episode_id"],
        )
        # O1=A: after generate, auto-register named on-screen roles missing from cast.
        # Does not unlock G1b or rewrite locked outline body (O2).
        rows, added = auto_merge_named_cast(
            rec,
            rows,
            alloc_char=self._alloc_char,
            one_line=AUTO_MERGE_ONE_LINE,
        )
        extra_warns: list[dict[str, Any]] = []
        if added:
            set_hint = getattr(self, "_set_cast_change_hint", None)
            if callable(set_hint):
                set_hint(rec, added=added, source="auto_merge")
            extra_warns.append(
                issue(
                    "warn",
                    NAMED_CAST_AUTO_MERGED,
                    "named on-screen roles auto-registered into cast",
                    added=added,
                )
            )
        issues = self._collect_sb_issues(rec, rows, shot_cap=cap, tool_profile=req.tool_profile)
        raise_hard(issues)
        sb["shot_cap"] = cap
        sb["rows"] = rows
        sb["shot_count"] = len(rows)
        sb["tool_profile"] = req.tool_profile
        sb["storyboard_skill"] = skill
        sb["skill_paths"] = [STORYBOARD_SKILL_PATH] if skill == "borrowed_dongman" else []
        sb["locked"] = False
        sb["confirmed_by"] = None
        sb["job_id"] = None
        rec["source_storyboard_skill"] = STORYBOARD_SKILL_PATH if skill == "borrowed_dongman" else None
        self._pin_upstream(rec, sb)
        self._finish_storyboard(rec, sb, actor=req.actor)
        self._commit(rec)
        warns = extra_warns + [i for i in issues if i.get("severity") == "warn"]
        return self._idem_put(
            idempotency_key,
            f"generate_storyboard:{project_id}:{ep}",
            self.storyboard_envelope(rec, warnings=warns or None),
        )

    def validate_storyboard(
        self,
        project_id: str,
        ep: str,
        *,
        raw: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_n2(raw)
        rec = self._rec(project_id, ep)
        self._require_g1b_for_n2(rec)
        sb = rec.get("storyboard") or self._empty_storyboard(rec)
        issues = self._collect_sb_issues(rec, sb.get("rows") or [], shot_cap=sb.get("shot_cap") or 12)
        if not (sb.get("rows") or []):
            issues.append(
                {
                    "severity": "error",
                    "code": "storyboard_empty",
                    "message": "storyboard has no rows",
                    "shot_id": None,
                    "field": "rows",
                }
            )
        valid = all(i.get("severity") != "error" for i in issues)
        ready = ready_for_n4(sb.get("tool_profile"), issues) and valid
        return {
            "ok": True,
            "project_id": project_id,
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN2,
            "valid": valid,
            "ready_for_n4": ready,
            "issues": issues,
            "storyboard": deepcopy(sb) if rec.get("storyboard") else sb,
        }

    def reorder_storyboard(
        self,
        project_id: str,
        ep: str,
        body: StoryboardReorderRequest,
        *,
        raw: dict[str, Any] | None = None,
        if_match: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_n2(raw)
        cached = self._idem_get(idempotency_key, f"reorder_storyboard:{project_id}:{ep}")
        if cached:
            return cached
        rec = self._rec(project_id, ep)
        self._require_g1b_for_n2(rec)
        if not rec.get("storyboard"):
            raise AppError(404, "not_found", "storyboard not found", node=NODE_DN2)
        sb = rec["storyboard"]
        check_if_match(if_match, sb.get("version") or 0, "storyboard")
        self._require_storyboard_unlock(rec, unlock_edit=False)
        current = {row["shot_id"]: row for row in sb.get("rows") or []}
        if set(body.shot_ids) != set(current):
            raise AppError(
                422,
                "seq_invalid",
                "shot_ids must be a permutation of current rows",
                shot_ids=body.shot_ids,
                node=NODE_DN2,
            )
        new_rows = []
        for seq, shot_id in enumerate(body.shot_ids, start=1):
            row = deepcopy(current[shot_id])
            row["seq"] = seq
            new_rows.append(row)
        sb["rows"] = new_rows
        sb["shot_count"] = len(new_rows)
        self._finish_storyboard(rec, sb, actor=body.actor)
        self._commit(rec)
        return self._idem_put(
            idempotency_key,
            f"reorder_storyboard:{project_id}:{ep}",
            self.storyboard_envelope(rec),
        )

    def reset_storyboard(
        self,
        project_id: str,
        ep: str,
        body: StoryboardResetRequest | None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_n2(raw)
        cached = self._idem_get(idempotency_key, f"reset_storyboard:{project_id}:{ep}")
        if cached:
            return cached
        rec = self._rec(project_id, ep)
        self._require_g1b_for_n2(rec)
        req = body or StoryboardResetRequest()
        sb = rec.get("storyboard") or self._empty_storyboard(rec)
        self._require_storyboard_unlock(rec, req.unlock_edit)
        cap = inherit_shot_cap((rec.get("outline") or {}).get("shot_cap") or sb.get("shot_cap"))
        sb["shot_cap"] = cap
        sb["rows"] = []
        sb["shot_count"] = 0
        sb["locked"] = False
        sb["confirmed_by"] = None
        sb["ready_for_n4"] = False
        sb["job_id"] = None
        self._pin_upstream(rec, sb)
        self._finish_storyboard(rec, sb, actor=req.actor)
        rec["gate_g2"]["state"] = "idle"
        self._commit(rec)
        return self._idem_put(
            idempotency_key,
            f"reset_storyboard:{project_id}:{ep}",
            self.storyboard_envelope(rec),
        )

    def get_gate_g2(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, ep)
        return self.gate_g2_envelope(rec)

    def confirm_gate_g2(
        self,
        project_id: str,
        ep: str,
        raw: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_n2(raw)
        extra = set(raw.keys()) - {"decision", "note", "actor", "idempotency_key"}
        if extra:
            raise AppError(400, "validation", "unexpected fields on gate confirm", fields=sorted(extra))
        cached = self._idem_get(idempotency_key or raw.get("idempotency_key"), f"confirm_g2:{project_id}:{ep}")
        if cached:
            return cached
        rec = self._rec(project_id, ep)
        self._require_writable_episode(rec)
        self._require_g1b_for_n2(rec)
        sb = rec.get("storyboard")
        if not sb:
            raise AppError(422, "storyboard_empty", "storyboard has no rows", node=NODE_DN2)
        if sb.get("stale"):
            raise AppError(
                409,
                "stale_upstream",
                "outline/cast bumped; refresh storyboard",
                stale=["d_n2"],
                node=NODE_DN2,
            )
        decision = raw.get("decision")
        actor = (raw.get("actor") or "").strip()
        if decision not in {"pass", "reject"}:
            raise AppError(422, "validation", "decision must be pass|reject")
        if not actor:
            raise AppError(422, "validation", "actor is required")
        note = raw.get("note")
        ts = now_iso()
        if decision == "pass":
            issues = self._collect_sb_issues(rec, for_pass=True)
            raise_hard(issues)
            leftover = blocking_named_cast_issues(issues)
            if leftover:
                raise AppError(
                    422,
                    NAMED_CAST_GATE,
                    G2_BLOCK_MESSAGE,
                    issues=leftover,
                    node=NODE_DN2,
                    gate=GATE_G2,
                )
            clear_hint = getattr(self, "_clear_cast_change_hint", None)
            if callable(clear_hint):
                clear_hint(rec)
            sb["locked"] = True
            sb["confirmed_by"] = actor
            sb["version"] = (sb.get("version") or 0) + 1
            sb["updated_at"] = ts
            sb["updated_by"] = actor
            sb["ready_for_n4"] = ready_for_n4(sb.get("tool_profile"), issues)
            rec["gate_g2"]["state"] = "passed"
            rec["gate_g2"]["locked"] = True
            rec["gate_g2"]["last_decision"] = "pass"
            rec["gate_g2"]["note"] = note
            rec["gate_g2"]["actor"] = actor
            rec["gate_g2"]["decided_at"] = ts
            rec["gate_g2"]["version"] = sb["version"]
            rec["episode"]["locks"]["g2"] = True
            rec["episode"]["next_edges"] = [NODE_DN3]
            rec["d_n3_jobs"] = []
        else:
            rec["gate_g2"]["state"] = "rejected"
            rec["gate_g2"]["locked"] = False
            rec["gate_g2"]["last_decision"] = "reject"
            rec["gate_g2"]["note"] = note
            rec["gate_g2"]["actor"] = actor
            rec["gate_g2"]["decided_at"] = ts
            rec["gate_g2"]["version"] = sb.get("version") or rec["gate_g2"]["version"]
            rec["episode"]["locks"]["g2"] = False
            rec["episode"]["next_edges"] = [NODE_DN2]
            sb["locked"] = False
            sb["confirmed_by"] = None
            sb["updated_at"] = ts
        rec["storyboard"] = sb
        self._touch_episode(rec)
        self._commit(rec)
        env = self.gate_g2_envelope(rec)
        return self._idem_put(idempotency_key or raw.get("idempotency_key"), f"confirm_g2:{project_id}:{ep}", env)

    def get_dn3_consumer(self, project_id: str, ep: str) -> dict[str, Any]:
        """Read-only surface for a future D-N3 consumer. Does not start D-N3."""
        rec = self._rec(project_id, ep)
        sb = rec.get("storyboard") or {}
        if not sb.get("locked"):
            raise AppError(
                409,
                "upstream_unlocked",
                "D-N2 G2 not locked",
                node=NODE_DN2,
                gate=GATE_G2,
            )
        return {
            "ok": True,
            "project_id": project_id,
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN2,
            "consumer": NODE_DN3,
            "started": False,
            "jobs": list(rec.get("d_n3_jobs") or []),
            "storyboard": deepcopy(sb),
            "next_edges": list(rec["episode"].get("next_edges") or []),
        }
