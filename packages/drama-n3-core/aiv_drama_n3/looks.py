"""AIV-031 looks tree path authority.

episodes/<ep>/n3/looks/{char|scene}/<card_id>/
  face_<view>.png | full_<view>.png | plate_<view>.png
  web_refs/   # provenance only — ENG hook
  meta.json   # optional — ENG hook (sku/seed)

BE owns mkdir + path strings. Live Seedream/wan write is ENG.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

LOOKS_ROOT_REL = "n3/looks"
KIND_DIR = {
    "character": "char",
    "char": "char",
    "scene": "scene",
}
CHAR_FILE_ROLES = frozenset({"face", "full"})
SCENE_FILE_ROLES = frozenset({"plate", "look"})
DEFAULT_VIEW = "front"
DEFAULT_EXT = "png"

# TODO(ENG): STYLE-REF prompt assembly / live image write into this tree.
# TODO(ENG): web_refs/src_<slug>_<nn>.{png,jpg,webp} + optional manifest.jsonl.


def looks_kind_dir(kind: str | None) -> str:
    key = (kind or "").strip().lower()
    if key not in KIND_DIR:
        raise ValueError(f"looks kind must be character|scene, got {kind!r}")
    return KIND_DIR[key]


def looks_filename(role: str, view: str | None = None, *, ext: str = DEFAULT_EXT) -> str:
    """CHAR: face_<view>.png / full_<view>.png; SCENE: plate_<view>.png."""
    clean_role = (role or "").strip().lower()
    clean_view = (view or DEFAULT_VIEW).strip().lower() or DEFAULT_VIEW
    suffix = (ext or DEFAULT_EXT).lstrip(".")
    return f"{clean_role}_{clean_view}.{suffix}"


def looks_relpath(
    episode_id: str,
    kind: str,
    card_id: str,
    *,
    filename: str | None = None,
) -> str:
    """Authority string: episodes/<ep>/n3/looks/{char|scene}/<card_id>[/file]."""
    ep = (episode_id or "").strip()
    ident = (card_id or "").strip()
    parts = ["episodes", ep, LOOKS_ROOT_REL, looks_kind_dir(kind), ident]
    if filename:
        parts.append(filename)
    return "/".join(parts)


def looks_card_dir(episode_dir: Path, kind: str, card_id: str) -> Path:
    return Path(episode_dir) / LOOKS_ROOT_REL / looks_kind_dir(kind) / card_id


def looks_web_refs_dir(episode_dir: Path, kind: str, card_id: str) -> Path:
    return looks_card_dir(episode_dir, kind, card_id) / "web_refs"


def ensure_looks_card_dirs(episode_dir: Path, kind: str, card_id: str) -> Path:
    """mkdir looks/{char|scene}/<card_id>/ and web_refs/. Returns card dir."""
    card_dir = looks_card_dir(episode_dir, kind, card_id)
    card_dir.mkdir(parents=True, exist_ok=True)
    looks_web_refs_dir(episode_dir, kind, card_id).mkdir(parents=True, exist_ok=True)
    return card_dir


def ensure_episode_looks_tree(episode_dir: Path, cards: list[dict[str, Any]] | None = None) -> Path:
    """Ensure n3/looks/{char,scene}/ and per-card dirs when cards are known."""
    root = Path(episode_dir) / LOOKS_ROOT_REL
    (root / "char").mkdir(parents=True, exist_ok=True)
    (root / "scene").mkdir(parents=True, exist_ok=True)
    for card in cards or []:
        ident = (card.get("id") or "").strip()
        kind = card.get("kind")
        if ident and kind in {"character", "scene"}:
            ensure_looks_card_dirs(episode_dir, kind, ident)
    return root


def dest_looks_file(
    episode_dir: Path,
    episode_id: str,
    kind: str,
    card_id: str,
    role: str,
    view: str | None = None,
) -> tuple[Path, str]:
    """Return (absolute dest path, refs[].path authority string). mkdir card dir."""
    filename = looks_filename(role, view)
    card_dir = ensure_looks_card_dirs(episode_dir, kind, card_id)
    dest = card_dir / filename
    rel = looks_relpath(episode_id, kind, card_id, filename=filename)
    return dest, rel
