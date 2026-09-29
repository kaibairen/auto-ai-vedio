from __future__ import annotations

import re

from aiv_drama.errors import AppError

CHAR_RE = re.compile(r"^CHAR-(\d+)$")
SCENE_RE = re.compile(r"^SCENE-(\d+)$")


def format_char(n: int) -> str:
    return f"CHAR-{n:02d}"


def format_scene(n: int) -> str:
    return f"SCENE-{n:02d}"


def parse_seq(prefix: str, ident: str) -> int | None:
    m = re.match(rf"^{prefix}-(\d+)$", ident)
    return int(m.group(1)) if m else None


def next_id(used: set[str], prefix: str, counter: int) -> tuple[str, int]:
    n = counter
    while True:
        n += 1
        ident = f"{prefix}-{n:02d}"
        if ident not in used:
            return ident, n


def require_known_or_omit(ident: str | None, allocated: set[str], kind: str) -> str | None:
    """Return existing id or None if omitted. Invented ids → 422 (T-C2)."""
    if ident is None or ident == "":
        return None
    if ident in allocated:
        return ident
    raise AppError(
        422,
        "validation",
        f"{kind} id is server-allocated; omit id for new rows",
        id=ident,
        kind=kind,
        node="D-N1",
    )
