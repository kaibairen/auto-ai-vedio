"""CHAR look Mode A / Mode B (NOTE-AIV-036-LOOK-MODE-AB · U-033).

Mode A (default): P-CHAR = face/full ref on disk. Missing face → hard 409.
Mode B (card-text / 合板): P-CHAR = ``usable_for_n4`` on a **human-reviewed**
look sheet. Missing face *file* must not 409. Generate-look never flips
usable=true (ForcePass=never · ≠自绿).

Mode B applies when an auditable ``look_mode=B`` flag is set (episode / n3 /
card) **or** that CHAR already has a reviewed sheet. Not a global forever pin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiv_drama_n3.cards import has_usable_ref, is_char_id

LOOK_MODE_A = "A"
LOOK_MODE_B = "B"
LOOK_MODE_KEY = "CHAR-LOOK-MODE"
LOOK_MODE_NOTE_ID = "NOTE-AIV-036-LOOK-MODE-AB"

MODE_B_ALIASES = frozenset(
    {
        "b",
        "mode_b",
        "mode-b",
        "card_text",
        "card-text",
        "sheet",
        "合板",
        "text",
    }
)
MODE_A_ALIASES = frozenset({"a", "mode_a", "mode-a", "face", "full"})

LOOK_USABLE_FALSE_MESSAGE = "usable_for_n4=false · Mode B 合板未人审（look.usable_for_n4≠true），拒绝写盘"
LOOK_USABLE_FALSE_REASON = "look_usable_for_n4_false"
MODE_B_COPY_ZH = "Mode B 卡文/合板路径：P-CHAR=人审合板 usable_for_n4，不因缺 face 文件单独拦截。"
MODE_A_COPY_ZH = "Mode A 脸图路径：须 face/full usable；缺脸仍拦截。"


@dataclass(frozen=True)
class CharLookPolicy:
    mode: str
    source: str
    card_id: str | None = None

    @property
    def mode_b(self) -> bool:
        return self.mode == LOOK_MODE_B


def _normalize_look_mode(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.upper() == LOOK_MODE_A or text.lower() in MODE_A_ALIASES:
        return LOOK_MODE_A
    if text.upper() == LOOK_MODE_B or text.lower() in MODE_B_ALIASES:
        return LOOK_MODE_B
    return None


def _explicit_look_mode(blob: dict[str, Any] | None) -> str | None:
    if not isinstance(blob, dict):
        return None
    for key in ("look_mode", "char_look_mode", "look_path"):
        mode = _normalize_look_mode(blob.get(key))
        if mode:
            return mode
    return None


def resolve_char_look_policy(
    rec: dict[str, Any] | None = None,
    card: dict[str, Any] | None = None,
    *,
    n3: dict[str, Any] | None = None,
) -> CharLookPolicy:
    """Per-CHAR Mode A/B. Card flag > episode/n3 flag > reviewed sheet > default A."""
    n3 = n3 if n3 is not None else (rec or {}).get("n3")
    card_mode = _explicit_look_mode(card)
    if card_mode:
        return CharLookPolicy(mode=card_mode, source="card_flag", card_id=(card or {}).get("id"))
    episode = (rec or {}).get("episode") or {}
    cards = (n3 or {}).get("cards") or {}
    for blob, source in ((episode, "episode_flag"), (n3, "n3_flag"), (cards, "cards_flag")):
        mode = _explicit_look_mode(blob)
        if mode:
            return CharLookPolicy(mode=mode, source=source, card_id=(card or {}).get("id"))
    if card is not None and has_reviewed_look_sheet(card, n3):
        return CharLookPolicy(mode=LOOK_MODE_B, source="reviewed_sheet", card_id=card.get("id"))
    return CharLookPolicy(mode=LOOK_MODE_A, source="default", card_id=(card or {}).get("id"))


def _iter_looks(card: dict[str, Any] | None, n3: dict[str, Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if card:
        for item in card.get("looks") or []:
            if isinstance(item, dict):
                out.append(item)
    ident = (card or {}).get("id")
    blob = ((n3 or {}).get("looks") or {}).get(ident) if ident else None
    if isinstance(blob, dict):
        out.append(blob)
    return out


def look_sheet_identity(look: dict[str, Any]) -> tuple[str, str]:
    path = (look.get("sheet_path") or look.get("path") or "").strip()
    md5 = (look.get("sheet_md5") or look.get("md5") or "").strip()
    return path, md5


def has_reviewed_look_sheet(card: dict[str, Any] | None, n3: dict[str, Any] | None = None) -> bool:
    """Human-reviewed 合板: look.usable_for_n4 is true. Never invent that flag."""
    if not card:
        return False
    if card.get("kind") != "character" and not is_char_id(card.get("id")):
        return False
    for look in _iter_looks(card, n3):
        if look.get("usable_for_n4") is not True:
            continue
        if look.get("dry_run"):
            continue
        path, md5 = look_sheet_identity(look)
        if not path or not md5 or look.get("missing_file"):
            continue
        role = (look.get("role") or "").strip()
        if role in {"face", "full"}:
            continue
        return True
    return False


def has_usable_char(card: dict[str, Any] | None, n3: dict[str, Any] | None = None) -> bool:
    """Mode A face/full **or** Mode B reviewed 合板. Does not invent usable=true."""
    if not card:
        return False
    if has_usable_ref(card):
        return True
    return has_reviewed_look_sheet(card, n3)


def reviewed_look_sheet_path(card: dict[str, Any] | None, n3: dict[str, Any] | None = None) -> str | None:
    for look in _iter_looks(card, n3):
        if look.get("usable_for_n4") is not True or look.get("dry_run"):
            continue
        path, md5 = look_sheet_identity(look)
        if path and md5 and not look.get("missing_file"):
            return path
    return None


def char_look_envelope_fields(
    rec: dict[str, Any] | None,
    *,
    n3: dict[str, Any] | None = None,
) -> dict[str, Any]:
    n3 = n3 if n3 is not None else (rec or {}).get("n3")
    characters = list(((n3 or {}).get("cards") or {}).get("characters") or [])
    modes = {resolve_char_look_policy(rec, card, n3=n3).mode for card in characters} or {LOOK_MODE_A}
    episode_policy = resolve_char_look_policy(rec, None, n3=n3)
    mode = LOOK_MODE_B if LOOK_MODE_B in modes or episode_policy.mode_b else LOOK_MODE_A
    fields: dict[str, Any] = {
        "char_look_mode": mode,
        "char_look_copy": MODE_B_COPY_ZH if mode == LOOK_MODE_B else MODE_A_COPY_ZH,
        "char_look_note": LOOK_MODE_NOTE_ID,
    }
    if mode == LOOK_MODE_B:
        fields[LOOK_MODE_KEY] = LOOK_MODE_B
    return fields
