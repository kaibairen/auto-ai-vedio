"""N5b ops: dry map + BLOCK submit + G5. Never POST Ark create."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from aiv_drama.errors import AppError
from aiv_drama.validate import now_iso
from aiv_drama_n4.ops import DramaN4Ops
from aiv_drama_n4.projection import read_prompts_jsonl
from aiv_drama_n5b.client import recorded_create_request
from aiv_drama_n5b.constants import (
    LIVE_JOB_ENV,
    PROMPTS_REQUIRED_MESSAGE,
    SEEDANCE_SKU_PRIMARY,
    SKELETON_ID,
)
from aiv_drama_n5b.gates import (
    empty_gate,
    g4_locked,
    live_job_allowed,
    refuse_skeleton_live_post,
    require_clips_for_g5_pass,
    require_g4_for_submit,
    require_live_job_flag,
)
from aiv_drama_n5b.map import map_jsonl_lines
from aiv_drama_n5b.models import N5bGateRequest, N5bSubmitRequest
from aiv_drama_n5b.persist import list_clip_inventory
from aiv_drama_n5b.validate import reject_force_keys_n5b
from aiv_schema.models import GATE_G4, GATE_G5, NODE_DN5B, PIPELINE_DRAMA


def empty_n5b(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "episode_id": rec["episode"]["episode_id"],
        "pipeline_profile": PIPELINE_DRAMA,
        "skeleton": True,
        "skeleton_id": SKELETON_ID,
        "posted": False,
        "jobs": [],
        "default_sku": SEEDANCE_SKU_PRIMARY,
    }


class DramaN5bOps(DramaN4Ops):
    """N5b skeleton. Mode B look review does not block submit code."""

    def _ensure_n5b_fields(self, rec: dict[str, Any]) -> None:
        rec["episode"]["locks"].setdefault("g4", False)
        rec["episode"]["locks"].setdefault("g5", False)
        rec["episode"]["versions"].setdefault("grids", 0)
        rec["episode"]["versions"].setdefault("clips", 0)
        if not rec.get("gate_g4"):
            rec["gate_g4"] = empty_gate(GATE_G4)
        if not rec.get("gate_g5"):
            rec["gate_g5"] = empty_gate(GATE_G5)
        rec.setdefault("n5b", None)
        rec.setdefault("d_n5b_jobs", [])

    def _n5b_episode_dir(self, rec: dict[str, Any]):
        return self.store.episode_dir(rec["episode"]["project_id"], rec["episode"]["episode_id"])

    def _n5b_lines(self, rec: dict[str, Any]) -> list[dict[str, Any]]:
        return read_prompts_jsonl(self._n5b_episode_dir(rec), rec["episode"]["episode_id"])

    def _n5b_mapped(self, rec: dict[str, Any], *, shot: str | None = None, model: str | None = None) -> list[dict[str, Any]]:
        lines = self._n5b_lines(rec)
        if not lines:
            return []
        return map_jsonl_lines(lines, shot_id=shot, model=model)

    def n5b_envelope(
        self,
        rec: dict[str, Any],
        *,
        extra: dict[str, Any] | None = None,
        shot: str | None = None,
    ) -> dict[str, Any]:
        n5b = deepcopy(rec.get("n5b") or empty_n5b(rec))
        episode_dir = self._n5b_episode_dir(rec)
        clips = list_clip_inventory(episode_dir)
        mapped = self._n5b_mapped(rec, shot=shot)
        env: dict[str, Any] = {
            "ok": True,
            "project_id": rec["episode"]["project_id"],
            "episode_id": rec["episode"]["episode_id"],
            "node": NODE_DN5B,
            "skeleton": True,
            "skeleton_id": SKELETON_ID,
            "posted": False,
            "live_job_allowed": live_job_allowed(self.settings),
            "live_job_env": LIVE_JOB_ENV,
            "g4_locked": g4_locked(rec),
            "g4": deepcopy(rec.get("gate_g4") or empty_gate(GATE_G4)),
            "g5": deepcopy(rec.get("gate_g5") or empty_gate(GATE_G5)),
            "n5b": n5b,
            "clips": clips,
            "mapped": mapped,
            "jobs": list(rec.get("d_n5b_jobs") or []),
            "default_sku": SEEDANCE_SKU_PRIMARY,
            "mode_b_look_blocks": False,
            "docs_pass": False,
            "auto_open_dn6": False,
            "next_edges": list(rec["episode"].get("next_edges") or []),
        }
        if extra:
            env.update(extra)
        return env

    def get_n5b_status(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, ep)
        return self.n5b_envelope(rec)

    def get_n5b_job(self, project_id: str, ep: str, job_id: str) -> dict[str, Any]:
        rec = self._rec(project_id, ep)
        for job in rec.get("d_n5b_jobs") or []:
            if job.get("id") == job_id or job.get("job_id") == job_id:
                return {"ok": True, "node": NODE_DN5B, "job": deepcopy(job), "posted": False, "skeleton": True}
        raise AppError(
            404,
            "not_found",
            "N5b skeleton 无真实 Job；未 POST create",
            node=NODE_DN5B,
            job_id=job_id,
            posted=False,
        )

    def submit_n5b(
        self,
        project_id: str,
        ep: str,
        body: N5bSubmitRequest | None = None,
        *,
        raw: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Always BLOCK live POST. Dry-map jsonl when G4 is locked."""
        reject_force_keys_n5b(raw)
        req = body or N5bSubmitRequest()
        rec = self._rec(project_id, ep)
        if rec["episode"].get("pipeline_profile") != PIPELINE_DRAMA:
            raise AppError(422, "wrong_profile", "pipeline_profile must be drama", node=NODE_DN5B)
        self._require_writable_episode(rec)
        extra = {
            "actor": req.actor,
            "shot": req.shot,
            "recorded": None,
        }
        mapped = self._n5b_mapped(rec, shot=req.shot, model=req.model)
        extra["mapped"] = mapped
        extra["prompts_present"] = bool(mapped) or bool(self._n5b_lines(rec))
        if mapped:
            extra["recorded"] = [recorded_create_request(item["body"], base_url=self.settings.ark_base_url) for item in mapped]
        require_g4_for_submit(rec, extra=extra)
        if not mapped:
            extra["prompts_present"] = False
            extra["block"] = "prompts_required"
            raise AppError(
                409,
                "prompts_required",
                PROMPTS_REQUIRED_MESSAGE,
                node=NODE_DN5B,
                posted=False,
                **extra,
            )
        require_live_job_flag(self.settings, extra=extra)
        refuse_skeleton_live_post(extra=extra)

    def get_gate_g5(self, project_id: str, ep: str) -> dict[str, Any]:
        rec = self._rec(project_id, ep)
        env = self.n5b_envelope(rec)
        return {
            "ok": True,
            "project_id": env["project_id"],
            "episode_id": env["episode_id"],
            "node": NODE_DN5B,
            "gate": env["g5"],
            "g4_locked": env["g4_locked"],
            "clips": env["clips"],
            "docs_pass": False,
            "auto_open_dn6": False,
        }

    def confirm_gate_g5(
        self,
        project_id: str,
        ep: str,
        raw: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        reject_force_keys_n5b(raw)
        extra_fields = set((raw or {}).keys()) - {"decision", "verdict", "note", "actor", "idempotency_key"}
        if extra_fields:
            raise AppError(400, "validation", "unexpected fields on G5 confirm", fields=sorted(extra_fields), node=NODE_DN5B)
        cached = self._idem_get(idempotency_key or (raw or {}).get("idempotency_key"), f"confirm_g5:{project_id}:{ep}")
        if cached:
            return cached
        rec = self._rec(project_id, ep)
        self._require_writable_episode(rec)
        body = N5bGateRequest.model_validate(raw or {})
        decision = (body.decision or body.verdict or "").strip()
        actor = (body.actor or "").strip()
        if decision not in {"pass", "rework"}:
            raise AppError(422, "validation", "decision/verdict must be pass|rework", node=NODE_DN5B, gate=GATE_G5)
        if not actor:
            raise AppError(422, "validation", "actor is required", node=NODE_DN5B, gate=GATE_G5)
        ts = now_iso()
        if decision == "pass":
            require_g4_for_submit(rec)
            require_clips_for_g5_pass(self._n5b_episode_dir(rec))
            rec["gate_g5"]["state"] = "passed"
            rec["gate_g5"]["locked"] = True
            rec["gate_g5"]["last_decision"] = "pass"
            rec["episode"]["locks"]["g5"] = True
        else:
            rec["gate_g5"]["state"] = "rework"
            rec["gate_g5"]["locked"] = False
            rec["gate_g5"]["last_decision"] = "rework"
            rec["episode"]["locks"]["g5"] = False
        rec["gate_g5"]["note"] = body.note
        rec["gate_g5"]["actor"] = actor
        rec["gate_g5"]["decided_at"] = ts
        rec["gate_g5"]["version"] = int(rec["gate_g5"].get("version") or 0) + 1
        self._touch_episode(rec)
        self._commit(rec)
        env = self.get_gate_g5(project_id, ep)
        return self._idem_put(idempotency_key or (raw or {}).get("idempotency_key"), f"confirm_g5:{project_id}:{ep}", env)
