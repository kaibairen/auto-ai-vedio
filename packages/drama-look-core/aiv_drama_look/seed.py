"""Same CHAR same seed; SCENE separate namespace. DESIGN-AIV-031-ENG §3."""

from __future__ import annotations

import hashlib
from typing import Any


def _namespace(kind: str) -> str:
    return "scene" if kind == "scene" else "char"


def derive_seed(card_id: str, kind: str) -> int:
    digest = hashlib.md5(f"{_namespace(kind)}:{card_id}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 2147483647


def seed_for_card(
    card_id: str,
    kind: str,
    *,
    existing_meta: dict[str, Any] | None = None,
    requested: int | None = None,
) -> int:
    """CHAR reuses meta.seed across views. SCENE never borrows a CHAR seed."""
    if requested is not None:
        return int(requested)
    if kind != "scene" and existing_meta and existing_meta.get("seed") is not None:
        return int(existing_meta["seed"])
    return derive_seed(card_id, kind)
