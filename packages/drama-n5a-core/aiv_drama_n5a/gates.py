"""N5a / G4 gates. ForcePass=never. jsonl required before generate. G4 before N5b."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aiv_drama.errors import AppError
from aiv_drama_n4.projection import prompts_jsonl_name, read_prompts_jsonl
from aiv_drama_n5a.checklist import veto_blocks_pass
from aiv_drama_n5a.validate import (
    EMPTY_JSONL_MESSAGE,
    G4_VETO_MESSAGE,
    MISSING_GRID_MESSAGE,
    MISSING_JSONL_MESSAGE,
    N5B_LOCKED_MESSAGE,
    N5B_NOT_IMPL_MESSAGE,
)
from aiv_schema.models import GATE_G4, NODE_DN5A, NODE_DN5B, PIPELINE_DRAMA


def empty_gate_g4() -> dict[str, Any]:
    return {
        "gate_id": GATE_G4,
        "state": "idle",
        "locked": False,
        "version": 0,
        "last_decision": None,
        "note": None,
        "actor": None,
        "decided_at": None,
    }


def empty_n5a(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "episode_id": rec["episode"]["episode_id"],
        "pipeline_profile": PIPELINE_DRAMA,
        "started": False,
        "stale": False,
        "grid_version": 0,
        "layout": None,
        "grid_relpath": None,
        "checklist_relpath": None,
        "evidence_relpath": None,
        "md5": None,
        "sku": None,
        "look_modes": {},
        "scene_exempt": False,
        "fake_pixels": False,
        "dry_run": False,
        "upstream_assemble_version": 0,
        "generated_at": None,
        "generated_by": None,
    }


def g4_locked(rec: dict[str, Any]) -> bool:
    g4 = rec.get("gate_g4") or {}
    return bool(g4.get("locked") and g4.get("last_decision") == "pass")


def load_prompts_or_409(episode_dir: Path, ep: str) -> list[dict[str, Any]]:
    path = episode_dir / prompts_jsonl_name(ep)
    if not path.is_file():
        raise AppError(
            409,
            "missing_prompts_jsonl",
            MISSING_JSONL_MESSAGE,
            node=NODE_DN5A,
            written=False,
            path=f"episodes/{ep}/{prompts_jsonl_name(ep)}",
        )
    lines = read_prompts_jsonl(episode_dir, ep)
    if not lines:
        raise AppError(
            409,
            "missing_prompts_jsonl",
            EMPTY_JSONL_MESSAGE,
            node=NODE_DN5A,
            written=False,
            path=f"episodes/{ep}/{prompts_jsonl_name(ep)}",
        )
    return lines


def require_jsonl_for_generate(episode_dir: Path, ep: str) -> list[dict[str, Any]]:
    return load_prompts_or_409(episode_dir, ep)


def require_g4_for_n5b(rec: dict[str, Any]) -> None:
    if rec["episode"].get("pipeline_profile") != PIPELINE_DRAMA:
        raise AppError(422, "wrong_profile", "pipeline_profile must be drama", node=NODE_DN5B)
    if not g4_locked(rec):
        raise AppError(
            409,
            "upstream_unlocked",
            N5B_LOCKED_MESSAGE,
            node=NODE_DN5A,
            gate=GATE_G4,
            consumer=NODE_DN5B,
        )


def reject_n5b_submit(rec: dict[str, Any]) -> None:
    require_g4_for_n5b(rec)
    raise AppError(
        404,
        "n5b_not_implemented",
        N5B_NOT_IMPL_MESSAGE,
        node=NODE_DN5B,
        gate=GATE_G4,
        n5b=False,
    )


def require_grid_for_g4_pass(
    *,
    rec: dict[str, Any],
    episode_dir: Path,
    checklist: dict[str, Any] | None,
) -> None:
    n5a = rec.get("n5a") or {}
    rel = n5a.get("grid_relpath")
    md5 = n5a.get("md5")
    if n5a.get("dry_run") or not rel or not md5:
        raise AppError(409, "missing_grid", MISSING_GRID_MESSAGE, node=NODE_DN5A, gate=GATE_G4)
    name = Path(rel).name
    path = episode_dir / "grids" / name
    if not path.is_file():
        raise AppError(409, "missing_grid", MISSING_GRID_MESSAGE, node=NODE_DN5A, gate=GATE_G4, path=rel)
    blocked = veto_blocks_pass(checklist)
    if blocked:
        raise AppError(
            409,
            "g4_veto_blocked",
            G4_VETO_MESSAGE,
            node=NODE_DN5A,
            gate=GATE_G4,
            veto=blocked,
        )


def n4_assemble_version(rec: dict[str, Any]) -> int:
    return int((rec.get("n4") or {}).get("assemble_version") or 0)
