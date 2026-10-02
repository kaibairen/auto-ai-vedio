"""N5b submit / G5 gates. ForcePass=never. G4 unread from N5a record only."""

from __future__ import annotations

import os
from typing import Any

from aiv_drama.errors import AppError
from aiv_drama_n5b.constants import (
    CLIPS_REQUIRED_MESSAGE,
    FAKE_PIXELS_MESSAGE,
    G4_REQUIRED_MESSAGE,
    IMPL_HOLD_MESSAGE,
    LIVE_JOB_ENV,
    LIVE_JOB_FORBIDDEN_MESSAGE,
)
from aiv_drama_n5b.persist import list_clip_inventory
from aiv_schema.models import GATE_G4, GATE_G5, NODE_DN5A, NODE_DN5B


def live_job_allowed(settings: Any | None = None) -> bool:
    if settings is not None:
        flag = getattr(settings, "n5b_allow_live_job", None)
        if flag is not None:
            return bool(flag)
    raw = (os.environ.get(LIVE_JOB_ENV) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def g4_locked(rec: dict[str, Any]) -> bool:
    """N5a writes gate_g4. N5b only reads. Mode B look review is not a hard block here."""
    g4 = rec.get("gate_g4") or {}
    if g4.get("locked") and g4.get("last_decision") == "pass":
        return True
    subset = g4.get("written_subset")
    if subset is True:
        return True
    if isinstance(subset, list) and len(subset) > 0:
        return True
    return bool((rec.get("episode") or {}).get("locks", {}).get("g4")) and g4.get("last_decision") == "pass"


def empty_gate(gate_id: str) -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "state": "idle",
        "locked": False,
        "version": 0,
        "last_decision": None,
        "note": None,
        "actor": None,
        "decided_at": None,
        "written_subset": None,
    }


def require_g4_for_submit(rec: dict[str, Any], *, extra: dict[str, Any] | None = None) -> None:
    if g4_locked(rec):
        return
    details: dict[str, Any] = {
        "node": NODE_DN5B,
        "gate": GATE_G4,
        "g4_locked": False,
        "posted": False,
        "block": "g4_required",
    }
    if extra:
        details.update(extra)
    raise AppError(409, "g4_required", G4_REQUIRED_MESSAGE, **details)


def require_live_job_flag(settings: Any | None, *, extra: dict[str, Any] | None = None) -> None:
    if live_job_allowed(settings):
        return
    details: dict[str, Any] = {
        "node": NODE_DN5B,
        "posted": False,
        "dry_run": True,
        "live_job_allowed": False,
        "live_job_env": LIVE_JOB_ENV,
        "block": "live_job_forbidden",
    }
    if extra:
        details.update(extra)
    raise AppError(409, "live_job_forbidden", LIVE_JOB_FORBIDDEN_MESSAGE, **details)


def refuse_skeleton_live_post(*, extra: dict[str, Any] | None = None) -> None:
    """Even with G4 + flag, this ASSIGN never POSTs create."""
    details: dict[str, Any] = {
        "node": NODE_DN5B,
        "posted": False,
        "skeleton": True,
        "live_job_allowed": True,
        "block": "n5b_impl_hold",
        "upstream": NODE_DN5A,
    }
    if extra:
        details.update(extra)
    raise AppError(409, "n5b_impl_hold", IMPL_HOLD_MESSAGE, **details)


def require_clips_for_g5_pass(episode_dir: Any) -> list[dict[str, Any]]:
    inventory = list_clip_inventory(episode_dir)
    complete = [item for item in inventory if item.get("complete")]
    if any(item.get("fake_pixels") for item in inventory):
        raise AppError(
            409,
            "fake_pixels_forbidden",
            FAKE_PIXELS_MESSAGE,
            node=NODE_DN5B,
            gate=GATE_G5,
            clips=inventory,
        )
    if not complete:
        raise AppError(
            409,
            "clips_required",
            CLIPS_REQUIRED_MESSAGE,
            node=NODE_DN5B,
            gate=GATE_G5,
            clips=inventory,
        )
    return complete
