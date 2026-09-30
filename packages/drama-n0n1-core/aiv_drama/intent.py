"""Episode-level intent confirm (018a scheme A). SoT is API store, not a dogfood file."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from aiv_drama.errors import AppError

NODE_INTENT = "D-N0"

INTENT_UNCONFIRMED = "intent_unconfirmed"
INTENT_STALE = "intent_stale"
INTENT_LANE_CONFLICT = "intent_lane_conflict"

MSG_UNCONFIRMED = "请先完成意图确认，再生成大纲。"
MSG_STALE = "意图字段已变更，请重新确认后再生成大纲。"
MSG_LANE_CONFLICT = "赛道与预挂频向冲突，请先一键跟预挂改 lane。"

_PROTAG_MARKERS = ("主角", "女主", "男主", "主人公")
_MALE_IDENTITY_RE = re.compile(r"(男主|男主角|男性|男生|·男|／男|/男)")
_FEMALE_IDENTITY_RE = re.compile(r"(女主|女主角|女性|女生|·女|／女|/女)")
PLACEHOLDER_ONE_LINES = frozenset({"", "待补一句话", "预挂角色"})

# Confirm / generate must not treat these as photography hard gates.
PHOTOGRAPHY_KEYS = frozenset(
    {
        "look",
        "look_ref",
        "look_uri",
        "costume",
        "makeup",
        "grid",
        "nine_grid",
        "ref_image",
        "reference_image",
        "prompt",
        "image_prompt",
        "定妆",
        "九宫",
        "服化",
    }
)


def empty_intent() -> dict[str, Any]:
    return {
        "confirmed": False,
        "fingerprint": None,
        "confirmed_at": None,
        "confirmed_by": None,
    }


def ensure_intent(rec: dict[str, Any]) -> dict[str, Any]:
    intent = rec.get("intent")
    if not isinstance(intent, dict):
        rec["intent"] = empty_intent()
        return rec["intent"]
    intent.setdefault("confirmed", False)
    intent.setdefault("fingerprint", None)
    intent.setdefault("confirmed_at", None)
    intent.setdefault("confirmed_by", None)
    return intent


def clear_intent_state(rec: dict[str, Any]) -> dict[str, Any]:
    rec["intent"] = empty_intent()
    return rec["intent"]


def is_protagonist_row(row: dict[str, Any]) -> bool:
    text = f"{row.get('name') or ''}{row.get('one_line') or ''}"
    return any(marker in text for marker in _PROTAG_MARKERS)


def infer_card_lane(card: dict[str, Any]) -> str | None:
    text = f"{card.get('name') or ''} {card.get('one_line') or ''}"
    male = bool(_MALE_IDENTITY_RE.search(text))
    female = bool(_FEMALE_IDENTITY_RE.search(text))
    if male and not female:
        return "male"
    if female and not male:
        return "female"
    return None


def select_hero(cards: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not cards:
        return None
    marked = [c for c in cards if c.get("is_hero") is True]
    if marked:
        return marked[0]
    protag = [c for c in cards if is_protagonist_row(c)]
    if protag:
        return protag[0]
    return cards[0]


def resolve_hero_one_line(brief: dict[str, Any] | None, cards: list[dict[str, Any]]) -> str:
    hero = select_hero(cards)
    if hero:
        line = (hero.get("one_line") or "").strip()
        if line and line not in PLACEHOLDER_ONE_LINES:
            return line
    return ((brief or {}).get("hero_one_line") or "").strip()


def pin_fingerprint_text(pin: Any) -> str:
    if pin is None:
        return ""
    if isinstance(pin, str):
        return pin.strip()
    if isinstance(pin, dict):
        raw = pin.get("raw")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return json.dumps(pin, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return str(pin).strip()


def fingerprint_payload(brief: dict[str, Any] | None, cards: list[dict[str, Any]]) -> dict[str, Any]:
    brief = brief or {}
    lane = brief.get("lane_preference") or "unset"
    if lane not in {"female", "male", "unset"}:
        lane = "unset"
    hero_card = select_hero(cards)
    hero_id = (hero_card or {}).get("id")
    preattach: list[dict[str, Any]] = []
    for card in cards:
        preattach.append(
            {
                "id": str(card.get("id") or ""),
                "name": (card.get("name") or "").strip(),
                "one_line": (card.get("one_line") or "").strip(),
                "is_hero": bool(hero_id) and card.get("id") == hero_id,
            }
        )
    preattach.sort(key=lambda row: row["id"])
    return {
        "lane": lane,
        "title_intent": (brief.get("title_intent") or "").strip(),
        "pin": pin_fingerprint_text(brief.get("pin")),
        "hero_one_line": resolve_hero_one_line(brief, cards),
        "preattach": preattach,
    }


def canonical_fingerprint_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def compute_intent_fingerprint(brief: dict[str, Any] | None, cards: list[dict[str, Any]]) -> str:
    raw = canonical_fingerprint_json(fingerprint_payload(brief, cards))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def analyze_lane_conflict(lane: str | None, cards: list[dict[str, Any]]) -> dict[str, Any]:
    current = lane if lane in {"female", "male", "unset"} else "unset"
    preattach_lanes = [inferred for card in cards if (inferred := infer_card_lane(card))]
    hero = select_hero(cards)
    hero_lane = infer_card_lane(hero) if hero else None
    conflicting = [
        inferred
        for card in cards
        if (inferred := infer_card_lane(card)) and current in {"female", "male"} and inferred != current
    ]
    conflict = bool(cards) and bool(conflicting)
    suggested = hero_lane if hero_lane in {"female", "male"} else (conflicting[0] if conflicting else None)
    return {
        "conflict": conflict,
        "suggested_lane": suggested if conflict else None,
        "current_lane": current,
        "preattach_lanes": preattach_lanes,
    }


def can_confirm(*, lane: str | None, brief: dict[str, Any] | None, cards: list[dict[str, Any]], title_ok: bool) -> bool:
    if lane not in {"female", "male"}:
        return False
    if not title_ok:
        return False
    if not resolve_hero_one_line(brief, cards):
        return False
    return not analyze_lane_conflict(lane, cards)["conflict"]


def maybe_clear_intent_on_must_change(rec: dict[str, Any], before_fp: str | None, after_fp: str | None) -> bool:
    intent = ensure_intent(rec)
    if not intent.get("confirmed"):
        return False
    if before_fp and after_fp and before_fp == after_fp:
        return False
    clear_intent_state(rec)
    return True


def reject_confirm_draft_hero(raw: dict[str, Any] | None) -> None:
    if isinstance(raw, dict) and "hero_one_line" in raw:
        raise AppError(
            422,
            "validation",
            "hero_one_line is not accepted on confirm; persist via brief or cast first",
            node=NODE_INTENT,
            field="hero_one_line",
        )


def photography_keys_present(raw: dict[str, Any] | None) -> list[str]:
    if not isinstance(raw, dict):
        return []
    return sorted(k for k in raw if k in PHOTOGRAPHY_KEYS)
