"""Materialize per-episode CHAR/SCENE working cards from cast only.

Full materialize rebuilds CHAR+SCENE from cast. Opt-in upsert_one_scene_card
creates or updates a single SCENE without touching CHAR cards.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from aiv_drama.ids import CHAR_RE, SCENE_RE
from aiv_drama_n2.named_cast import (
    is_b_class,
    is_group_label,
    is_scene_b_class,
    is_system_speaker,
)

NONE_IDS = frozenset({"NONE", "none", "None"})
CHAR_ID_RE = CHAR_RE
SCENE_ID_RE = SCENE_RE


def is_char_id(ident: str | None) -> bool:
    return bool(ident and CHAR_ID_RE.match(ident))


def is_scene_id(ident: str | None) -> bool:
    return bool(ident and SCENE_ID_RE.match(ident))


def is_none_id(ident: str | None) -> bool:
    return (ident or "") in NONE_IDS or ident is None or ident == ""


def infer_kind(ident: str) -> str | None:
    if is_char_id(ident):
        return "character"
    if is_scene_id(ident):
        return "scene"
    return None


def binding_label(library_ref: dict[str, Any] | None) -> str:
    if not library_ref:
        return "local"
    ident = library_ref.get("id") or ""
    ver = library_ref.get("version")
    if ident and ver is not None:
        return f"{ident}@{ver}"
    return "attached"


def has_usable_ref(card: dict[str, Any]) -> bool:
    kind = card.get("kind")
    for ref in card.get("refs") or []:
        if not isinstance(ref, dict):
            continue
        path = (ref.get("path") or "").strip()
        md5 = (ref.get("md5") or "").strip()
        if not path or not md5:
            continue
        role = (ref.get("role") or "").strip()
        if kind == "character" and role not in {"face", "full"}:
            continue
        if not ref.get("missing_file", False):
            return True
    return False


def skip_cast_row(row: dict[str, Any], *, kind: str | None = None) -> bool:
    """Do not promote system-voice / crowd / NONE / CHAR-dirt to a working card.

    CHAR and SCENE use separate B-class buckets (023 F2). Spatial SCENE names
    must not inherit CHAR clause/开源/length punches.
    """
    ident = row.get("id") or ""
    name = row.get("name") or ""
    if is_none_id(ident) or ident in NONE_IDS:
        return True
    scene = kind == "scene" or is_scene_id(ident)
    if scene:
        if is_scene_b_class(name):
            return True
        return not is_scene_id(ident)
    if row.get("library_ref"):
        return not is_char_id(ident)
    if is_system_speaker(name) or is_group_label(name) or is_b_class(name):
        return True
    if not is_char_id(ident):
        return True
    return False


def _used_ids_from_storyboard(storyboard: dict[str, Any] | None) -> tuple[set[str], set[str]]:
    chars: set[str] = set()
    scenes: set[str] = set()
    for row in (storyboard or {}).get("rows") or []:
        for cid in row.get("char_ids") or []:
            if not is_none_id(cid) and is_char_id(cid):
                chars.add(cid)
        sid = row.get("scene_id")
        if not is_none_id(sid) and is_scene_id(sid):
            scenes.add(sid)
    return chars, scenes


def card_from_cast_row(
    row: dict[str, Any],
    *,
    kind: str,
    used: set[str],
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ident = row["id"]
    lib = deepcopy(row.get("library_ref")) if row.get("library_ref") else None
    prev = previous or {}
    refs = deepcopy(prev.get("refs") or [])
    missing = not has_usable_ref({"kind": kind, "refs": refs})
    tags = list(prev.get("status_tags") or [])
    if ident not in used and "预挂未上场" not in tags:
        tags.append("预挂未上场")
    if ident in used:
        tags = [t for t in tags if t != "预挂未上场"]
    origin = "attached" if lib else (prev.get("origin") or "local")
    return {
        "id": ident,
        "kind": kind,
        "name": row.get("name") or prev.get("name") or ident,
        "one_line": row.get("one_line") or prev.get("one_line") or "",
        "origin": origin,
        "library_ref": lib,
        "binding": binding_label(lib),
        "refs": refs,
        "missing_ref": missing,
        "weak_binding": missing,
        "status_tags": tags,
        "appearance": prev.get("appearance"),
        "immutable": prev.get("immutable"),
        "light_anchor": prev.get("light_anchor"),
        "crop_hints": prev.get("crop_hints"),
        "decision": None,
        "template_status": prev.get("template_status")
        or ("deferred" if kind == "scene" else None),
        "template_path": None if kind == "scene" else prev.get("template_path"),
    }


def materialize_cards(
    cast: dict[str, Any] | None,
    storyboard: dict[str, Any] | None,
    previous: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (characters, scenes, skipped_warnings). Never invents IDs."""
    used_chars, used_scenes = _used_ids_from_storyboard(storyboard)
    prev_chars = {c["id"]: c for c in ((previous or {}).get("characters") or [])}
    prev_scenes = {s["id"]: s for s in ((previous or {}).get("scenes") or [])}
    skipped: list[dict[str, Any]] = []
    characters: list[dict[str, Any]] = []
    scenes: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in (cast or {}).get("characters") or []:
        ident = row.get("id")
        if ident in seen:
            continue
        if skip_cast_row(row, kind="character") or not is_char_id(ident):
            skipped.append(
                {
                    "severity": "warn",
                    "code": "b_class_skipped",
                    "message": "系统音/群杂/B 档不开 CHAR 卡（沿 N2 / FIX-020 F1）",
                    "id": ident,
                    "name": row.get("name"),
                }
            )
            continue
        seen.add(ident)
        characters.append(card_from_cast_row(row, kind="character", used=used_chars, previous=prev_chars.get(ident)))

    for row in (cast or {}).get("scenes") or []:
        ident = row.get("id")
        if ident in seen:
            continue
        if skip_cast_row(row, kind="scene") or not is_scene_id(ident):
            skipped.append(
                {
                    "severity": "warn",
                    "code": "b_class_skipped",
                    "message": "不合规 SCENE 不开场景卡",
                    "id": ident,
                    "name": row.get("name"),
                }
            )
            continue
        seen.add(ident)
        scenes.append(card_from_cast_row(row, kind="scene", used=used_scenes, previous=prev_scenes.get(ident)))

    return characters, scenes, skipped


def resolve_scene_row(
    ident: str,
    cast: dict[str, Any] | None,
    *,
    name: str | None = None,
    one_line: str | None = None,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge one SCENE row from request / cast / existing card. Does not invent CHAR rows."""
    existing = next((s for s in (cast or {}).get("scenes") or [] if s.get("id") == ident), None)
    prev = previous or {}
    resolved_name = (name or "").strip() or (existing or {}).get("name") or prev.get("name") or ""
    resolved_one_line = (
        (one_line or "").strip() or (existing or {}).get("one_line") or prev.get("one_line") or ""
    )
    lib = None
    if existing and existing.get("library_ref"):
        lib = deepcopy(existing.get("library_ref"))
    elif prev.get("library_ref"):
        lib = deepcopy(prev.get("library_ref"))
    return {
        "id": ident,
        "name": resolved_name,
        "one_line": resolved_one_line,
        "library_ref": lib,
    }


def _apply_used_scene_tags(card: dict[str, Any], used: set[str]) -> None:
    ident = card.get("id") or ""
    tags = list(card.get("status_tags") or [])
    if ident not in used and "预挂未上场" not in tags:
        tags.append("预挂未上场")
    if ident in used:
        tags = [t for t in tags if t != "预挂未上场"]
    card["status_tags"] = tags


def upsert_one_scene_card(
    ident: str,
    cast: dict[str, Any] | None,
    storyboard: dict[str, Any] | None,
    previous: dict[str, Any] | None = None,
    *,
    name: str | None = None,
    one_line: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any], list[dict[str, Any]]]:
    """Create or update one SCENE working card. Never rebuilds CHAR cards.

    Storyboard scene_id is a used-set only; a missing cast.scenes row is allowed
    when name + one_line can be resolved (request, existing card, or cast).
    Returns (card_or_none, cast_row, skipped_warnings).
    """
    _used_chars, used_scenes = _used_ids_from_storyboard(storyboard)
    prev_scenes = {s["id"]: s for s in ((previous or {}).get("scenes") or []) if s.get("id")}
    prev = prev_scenes.get(ident)
    row = resolve_scene_row(ident, cast, name=name, one_line=one_line, previous=prev)
    skipped: list[dict[str, Any]] = []
    if not (row.get("name") or "").strip() or not (row.get("one_line") or "").strip():
        return None, row, skipped
    if skip_cast_row(row, kind="scene") or not is_scene_id(ident):
        skipped.append(
            {
                "severity": "warn",
                "code": "b_class_skipped",
                "message": "不合规 SCENE 不开场景卡",
                "id": ident,
                "name": row.get("name"),
            }
        )
        return None, row, skipped
    if prev:
        card = deepcopy(prev)
        card["id"] = ident
        card["kind"] = "scene"
        if row.get("name"):
            card["name"] = row["name"]
        if row.get("one_line"):
            card["one_line"] = row["one_line"]
        if row.get("library_ref") is not None:
            card["library_ref"] = deepcopy(row.get("library_ref"))
            card["binding"] = binding_label(row.get("library_ref"))
            card["origin"] = "attached"
        _apply_used_scene_tags(card, used_scenes)
        card["template_status"] = card.get("template_status") or "deferred"
        card["template_path"] = None
        return card, row, skipped
    return card_from_cast_row(row, kind="scene", used=used_scenes, previous=None), row, skipped


def all_cards(n3: dict[str, Any] | None) -> list[dict[str, Any]]:
    cards = (n3 or {}).get("cards") or {}
    return list(cards.get("characters") or []) + list(cards.get("scenes") or [])
