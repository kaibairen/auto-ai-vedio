"""Assemble-time hard gates. ForcePass=never. PRD+ENG win.

assemble write iff G2_locked and G3_locked and ready_for_n4 and usable_for_n4.
usable_for_n4_false → HTTP 409, no jsonl write, honest missing_refs.
SCENE look is hard only off the EXEMPT/optional path (NOTE-AIV-036 · proj_01/EP01).
CHAR usable stays a hard gate.
"""

from __future__ import annotations

from typing import Any

from aiv_drama.errors import AppError
from aiv_drama_n3.char_look import LOOK_USABLE_FALSE_MESSAGE, LOOK_USABLE_FALSE_REASON, char_look_envelope_fields
from aiv_drama_n3.scene_look import (
    CHAR_USABLE_FALSE_MESSAGE,
    scene_look_envelope_fields,
    resolve_scene_look_policy,
)
from aiv_drama_n3.validate import usable_for_n4
from aiv_drama_n4.validate import (
    STALE_UPSTREAM_MESSAGE,
    UPSTREAM_G2_MESSAGE,
    UPSTREAM_G3_MESSAGE,
    USABLE_FALSE_MESSAGE,
    collect_missing_refs,
    collect_scene_missing_refs,
)
from aiv_schema.models import GATE_G2, GATE_G3, NODE_DN2, NODE_DN3, NODE_DN4, PIPELINE_DRAMA

NOT_READY_MESSAGE = "ready_for_n4=false · 未选 tool_profile 或分镜硬检未过，拒绝写盘"


def g2_locked(rec: dict[str, Any]) -> bool:
    g2 = rec.get("gate_g2") or {}
    sb = rec.get("storyboard") or {}
    return bool(g2.get("locked") and g2.get("last_decision") == "pass" and sb.get("locked"))


def g3_locked(rec: dict[str, Any]) -> bool:
    g3 = rec.get("gate_g3") or {}
    cards = ((rec.get("n3") or {}).get("cards") or {})
    return bool(g3.get("locked") and g3.get("last_decision") == "pass" and cards.get("locked"))


def episode_ready_for_n4(rec: dict[str, Any]) -> bool:
    sb = rec.get("storyboard") or {}
    if not (sb.get("tool_profile") or "").strip():
        return False
    return bool(sb.get("ready_for_n4"))


def episode_usable_for_n4(rec: dict[str, Any], settings: Any | None = None) -> tuple[bool, list[dict[str, Any]]]:
    missing = collect_missing_refs(rec.get("n3"), settings, rec=rec)
    usable = usable_for_n4(rec.get("n3"), g3_locked=g3_locked(rec), rec=rec) and not missing
    return usable, missing


def require_g3_for_n4_read(rec: dict[str, Any]) -> None:
    if not g3_locked(rec):
        raise AppError(
            409,
            "upstream_unlocked",
            UPSTREAM_G3_MESSAGE,
            node=NODE_DN3,
            gate=GATE_G3,
        )


def require_assemble_gates(
    rec: dict[str, Any],
    settings: Any | None = None,
    *,
    force_reassemble: bool = False,
) -> list[dict[str, Any]]:
    """Raise the first hard gate. Returns missing_refs (empty on success)."""
    if rec["episode"].get("pipeline_profile") != PIPELINE_DRAMA:
        raise AppError(422, "wrong_profile", "pipeline_profile must be drama", node=NODE_DN4)
    if not g2_locked(rec):
        raise AppError(
            409,
            "upstream_unlocked",
            UPSTREAM_G2_MESSAGE,
            node=NODE_DN2,
            gate=GATE_G2,
        )
    if not g3_locked(rec):
        raise AppError(
            409,
            "upstream_unlocked",
            UPSTREAM_G3_MESSAGE,
            node=NODE_DN3,
            gate=GATE_G3,
        )
    if not episode_ready_for_n4(rec):
        raise AppError(
            409,
            "not_ready_for_n4",
            NOT_READY_MESSAGE,
            node=NODE_DN4,
            ready_for_n4=False,
            written=False,
            tool_profile=(rec.get("storyboard") or {}).get("tool_profile"),
        )
    usable, missing = episode_usable_for_n4(rec, settings)
    if not usable:
        policy = resolve_scene_look_policy(rec)
        scene_missing = collect_scene_missing_refs(rec.get("n3"), settings) if policy.scene_optional else []
        look_block = any(item.get("reason") == LOOK_USABLE_FALSE_REASON for item in missing)
        if look_block:
            msg = LOOK_USABLE_FALSE_MESSAGE
            en = "usable_for_n4 is false; Mode B look sheet is not human-reviewed — jsonl not written"
        elif policy.scene_optional:
            msg = CHAR_USABLE_FALSE_MESSAGE
            en = "usable_for_n4 is false; missing CHAR face/full — jsonl not written"
        else:
            msg = USABLE_FALSE_MESSAGE
            en = "usable_for_n4 is false; missing refs/images — jsonl not written"
        details = scene_look_envelope_fields(policy, scene_missing_refs=scene_missing)
        details.update(char_look_envelope_fields(rec))
        raise AppError(
            409,
            "usable_for_n4_false",
            msg,
            messages={"zh": msg, "en": en},
            usable_for_n4=False,
            missing_refs=missing,
            written=False,
            node=NODE_DN4,
            **details,
        )
    cards = ((rec.get("n3") or {}).get("cards") or {})
    if cards.get("stale") and not force_reassemble:
        raise AppError(409, "stale_upstream", STALE_UPSTREAM_MESSAGE, stale=["d_n3", "d_n4"], node=NODE_DN4)
    return missing
