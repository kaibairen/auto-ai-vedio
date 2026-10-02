"""Looks tree wrappers over BE aiv_drama_n3.looks (DESIGN-AIV-031-LOOK §1–§2).

Authority string: episodes/<ep>/n3/looks/{char|scene}/<card_id>/{role}_{view}.png
First-round dogfood: CHAR face_front · SCENE plate_empty.
"""

from __future__ import annotations

from pathlib import Path

from aiv_drama.errors import AppError
from aiv_drama_n3.looks import (
    ensure_looks_card_dirs,
    looks_card_dir,
    looks_filename,
    looks_relpath as be_looks_relpath,
    looks_web_refs_dir,
)
from aiv_drama_n3.refs import is_hotlink_url, reject_hotlink_path as be_reject_hotlink_path
from aiv_schema.models import NODE_DN3

KIND_CHAR = "character"
KIND_SCENE = "scene"

CHAR_USABLE_ROLES = frozenset({"face", "full"})
SCENE_ROLES = frozenset({"plate", "look"})
PROVENANCE_ROLES = frozenset({"style_ref", "web_source"})
ALLOWED_ROLES = CHAR_USABLE_ROLES | SCENE_ROLES | PROVENANCE_ROLES
ALLOWED_VIEWS = frozenset({"front", "side", "three_quarter", "empty", "ls"})


def kind_bucket(kind: str) -> str:
    if kind == KIND_SCENE:
        return "scene"
    return "char"


def default_view(kind: str) -> str:
    """First-round: CHAR 正面 CU · SCENE 空镜 LS."""
    return "empty" if kind == KIND_SCENE else "front"


def default_role(kind: str) -> str:
    return "plate" if kind == KIND_SCENE else "face"


def looks_relpath(episode_id: str, kind: str, card_id: str, role: str, view: str) -> str:
    """Canonical refs[].path (DESIGN example). Resolvable via normalize_refs."""
    return be_looks_relpath(episode_id, kind, card_id, filename=looks_filename(role, view))


def looks_absdir(episode_dir: Path, kind: str, card_id: str) -> Path:
    return looks_card_dir(episode_dir, kind, card_id)


def looks_abspath(episode_dir: Path, kind: str, card_id: str, role: str, view: str) -> Path:
    return looks_card_dir(episode_dir, kind, card_id) / looks_filename(role, view)


def web_refs_dir(episode_dir: Path, kind: str, card_id: str) -> Path:
    return looks_web_refs_dir(episode_dir, kind, card_id)


def reject_hotlink_path(path: str | None) -> str:
    text = (path or "").strip()
    if not text:
        raise AppError(422, "validation", "refs[].path 不可为空", node=NODE_DN3, field="path")
    return be_reject_hotlink_path(text)


def validate_role(kind: str, role: str) -> str:
    chosen = (role or "").strip()
    if chosen not in ALLOWED_ROLES:
        raise AppError(422, "validation", f"role 须为 {sorted(ALLOWED_ROLES)}", role=chosen, node=NODE_DN3)
    if kind == KIND_CHAR and chosen in SCENE_ROLES:
        raise AppError(422, "validation", "CHAR 主锚 role 须为 face|full（plate 仅 SCENE）", role=chosen, node=NODE_DN3)
    if kind == KIND_SCENE and chosen in CHAR_USABLE_ROLES:
        raise AppError(422, "validation", "SCENE 建议 plate|look，勿用 face 冒充定妆主锚", role=chosen, node=NODE_DN3)
    return chosen


def validate_view(view: str) -> str:
    chosen = (view or "").strip()
    if chosen not in ALLOWED_VIEWS:
        raise AppError(422, "validation", f"view 须为 {sorted(ALLOWED_VIEWS)}", view=chosen, node=NODE_DN3)
    return chosen


def ensure_card_looks_dirs(episode_dir: Path, kind: str, card_id: str) -> Path:
    return ensure_looks_card_dirs(episode_dir, kind, card_id)
