"""CHAR-/SCENE- ID → Chinese immutable features. Never leave a bare ID as the subject."""

from __future__ import annotations

from typing import Any

from aiv_drama_n3.cards import all_cards, is_char_id
from aiv_drama_n4.validate import BARE_ID_RE


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _appearance_text(appearance: Any) -> str:
    if isinstance(appearance, dict):
        return "，".join(_text(v) for v in appearance.values() if _text(v))
    return _text(appearance)


def _immutable_text(immutable: Any) -> str:
    if isinstance(immutable, dict):
        return "，".join(_text(v) for v in immutable.values() if _text(v))
    if isinstance(immutable, list):
        return "，".join(_text(v) for v in immutable if _text(v))
    return _text(immutable)


def card_features(card: dict[str, Any] | None, *, kind: str) -> str:
    """ID → 中文特征. Empty string if the card is missing or only a bare ID."""
    if not card:
        return ""
    name = _text(card.get("name"))
    one_line = _text(card.get("one_line"))
    extra = _appearance_text(card.get("appearance"))
    immutable = _immutable_text(card.get("immutable"))
    parts = [p for p in (name, immutable, one_line, extra) if p and not BARE_ID_RE.fullmatch(p)]
    return "，".join(dict.fromkeys(parts))


def card_index(n3: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in all_cards(n3) if c.get("id")}


def feature_catalog(n3: dict[str, Any] | None) -> dict[str, str]:
    catalog: dict[str, str] = {}
    for card in all_cards(n3):
        ident = card.get("id")
        if not ident:
            continue
        kind = "character" if is_char_id(ident) else "scene"
        catalog[ident] = card_features(card, kind=kind)
    return catalog


def replace_ids(text: str, catalog: dict[str, str]) -> str:
    def _repl(match):
        ident = match.group(0)
        return catalog.get(ident) or catalog.get(ident.upper()) or ident

    return BARE_ID_RE.sub(_repl, text or "")


def assert_no_bare_ids(text: str) -> bool:
    return BARE_ID_RE.search(text or "") is None


def card_version(card: dict[str, Any] | None) -> int | None:
    if not card:
        return None
    lib = card.get("library_ref") or {}
    if isinstance(lib, dict) and lib.get("version") is not None:
        try:
            return int(lib["version"])
        except (TypeError, ValueError):
            return None
    return None
