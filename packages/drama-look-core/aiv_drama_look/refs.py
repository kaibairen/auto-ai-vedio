"""Append refs[{path,md5,role}] without flipping usable_for_n4. ForcePass=never."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from aiv_drama.errors import AppError
from aiv_drama_look.paths import CHAR_USABLE_ROLES, reject_hotlink_path
from aiv_drama_n3.refs import has_usable_ref, md5_file, refresh_card_ref_flags
from aiv_schema.models import NODE_DN3


def md5_bytes(data: bytes) -> str:
    import hashlib

    if not data:
        raise AppError(422, "validation", "禁空文件占位 / 跳过 md5", node=NODE_DN3)
    return hashlib.md5(data).hexdigest()


def md5_existing(path: Path) -> str:
    if not path.is_file() or path.stat().st_size <= 0:
        raise AppError(422, "validation", "禁空文件占位 / 跳过 md5", path=str(path), node=NODE_DN3)
    digest = md5_file(path)
    if not digest:
        raise AppError(422, "validation", "禁空 md5 入卡", path=str(path), node=NODE_DN3)
    return digest


def make_ref(*, path: str, md5: str, role: str) -> dict[str, Any]:
    local = reject_hotlink_path(path)
    digest = (md5 or "").strip()
    if not digest:
        raise AppError(422, "validation", "禁空 md5 入卡", node=NODE_DN3, field="md5")
    return {"path": local, "md5": digest, "role": role}


def append_ref(card: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any]:
    """Hang path+md5+role. Never sets usable_for_n4."""
    updated = deepcopy(card)
    item = make_ref(path=ref.get("path"), md5=ref.get("md5") or "", role=ref.get("role") or "")
    refs = [r for r in (updated.get("refs") or []) if isinstance(r, dict)]
    out: list[dict[str, Any]] = []
    replaced = False
    for existing in refs:
        same_path = (existing.get("path") or "") == item["path"]
        same_role = (existing.get("role") or "") == item["role"]
        if same_path or (same_role and _same_look_slot(existing.get("path"), item["path"])):
            if not replaced:
                out.append(item)
                replaced = True
            continue
        out.append(deepcopy(existing))
    if not replaced:
        out.append(item)
    updated["refs"] = out
    refresh_card_ref_flags(updated)
    updated.pop("usable_for_n4", None)
    return updated


def _same_look_slot(left: str | None, right: str | None) -> bool:
    return Path(left or "").name == Path(right or "").name and bool(left) and bool(right)


def char_has_face_or_full(card: dict[str, Any]) -> bool:
    return has_usable_ref(card)


def only_provenance_roles(card: dict[str, Any]) -> bool:
    """True when CHAR refs exist but none are face|full (style_ref/web_source only)."""
    if card.get("kind") != "character":
        return False
    refs = [r for r in (card.get("refs") or []) if isinstance(r, dict)]
    if not refs:
        return False
    return not any((r.get("role") or "").strip() in CHAR_USABLE_ROLES for r in refs)
