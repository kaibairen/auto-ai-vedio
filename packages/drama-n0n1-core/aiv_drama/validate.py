from __future__ import annotations

import re
from typing import Any

from aiv_drama.config import SHOT_CAP_HARD
from aiv_drama.errors import AppError

EP_RE = re.compile(r"^EP\d{2,}$")
CHAR_NUM_RE = re.compile(r"^CHAR-(\d+)$")
SCENE_NUM_RE = re.compile(r"^SCENE-(\d+)$")

FORCE_KEYS = ("force_pass", "force", "skip_gate")

PROMPT_MARKERS = (
    "宫格",
    "提示词",
    "seedance",
    "[imagen",
    "负面提示词",
    "分镜表",
    "9宫格",
    "16宫格",
    "25宫格",
    "[image1]",
    "[image2]",
    "检g1",
    "检 g1",
)


def now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_ep(ep: str) -> str:
    if not EP_RE.match(ep or ""):
        raise AppError(422, "validation", "episode_id must match ^EP\\d{2,}$", episode_id=ep)
    return ep


def reject_force_keys(body: dict[str, Any] | None) -> None:
    if not isinstance(body, dict):
        return
    for key in FORCE_KEYS:
        if key in body:
            raise AppError(
                400,
                "force_pass_forbidden",
                "ForcePass=never",
                field=key,
                node="D-N1",
                gate="g1b",
            )


def reject_dual_skill(body: dict[str, Any] | None) -> None:
    if isinstance(body, dict) and "dual_skill_preview" in body:
        raise AppError(
            400,
            "validation",
            "dual_skill_preview is disabled (C1 / D3 provisional)",
            provisional="D3",
            node="D-N1",
        )


def pin_nonempty(pin: Any) -> bool:
    if not isinstance(pin, dict) or not pin:
        return False

    def leaf(v: Any) -> bool:
        if v is None:
            return False
        if isinstance(v, str):
            return bool(v.strip())
        if isinstance(v, (list, tuple)):
            return any(leaf(x) for x in v)
        if isinstance(v, dict):
            return any(leaf(x) for x in v.values())
        return True

    return leaf(pin)


def brief_ready(title_intent: str | None, pin: Any) -> bool:
    title_ok = bool((title_intent or "").strip())
    return title_ok or pin_nonempty(pin)


def require_brief_ready(title_intent: str | None, pin: Any) -> None:
    if not brief_ready(title_intent, pin):
        raise AppError(422, "brief_incomplete", "title_intent and pin both empty")


def outline_contains_prompts(body_md: str) -> bool:
    text = (body_md or "").lower()
    for marker in PROMPT_MARKERS:
        if marker.lower() in text:
            return True
    return False


def reject_outline_prompts(body_md: str) -> None:
    if outline_contains_prompts(body_md):
        raise AppError(
            422,
            "outline_contains_prompts",
            "outline must not contain prompts / 宫格 / Seedance / 出片 parameters",
            node="D-N1",
        )


def outline_has_beats(body_md: str) -> bool:
    text = body_md or ""
    if "桥段" not in text:
        return False
    if re.search(r"^\s*\d+\s*[\.、\)]\s+\S+", text, re.M):
        return True
    if re.search(r"^\s*[-*]\s+\S+", text, re.M):
        return True
    return False


def require_outline_beats(body_md: str) -> None:
    if not outline_has_beats(body_md):
        raise AppError(422, "outline_empty", "outline needs a numbered 桥段 sequence", node="D-N1")


def require_shot_cap(shot_cap: int | None) -> int:
    cap = SHOT_CAP_HARD if shot_cap is None else int(shot_cap)
    if cap < 1:
        raise AppError(422, "validation", "shot_cap must be >= 1")
    if cap > SHOT_CAP_HARD:
        raise AppError(
            422,
            "shot_cap_exceeded",
            f"shot_cap hard cap is {SHOT_CAP_HARD}",
            shot_cap=cap,
            hard_cap=SHOT_CAP_HARD,
        )
    return cap


def check_if_match(header: str | None, version: int, resource: str) -> None:
    if header is None or header == "":
        return
    raw = header.strip().strip('"')
    try:
        got = int(raw)
    except ValueError:
        raise AppError(
            409,
            "version_conflict",
            "If-Match mismatch",
            expected=version,
            actual=raw,
            resource=resource,
        ) from None
    if got != version:
        raise AppError(
            409,
            "version_conflict",
            "If-Match mismatch",
            expected=version,
            actual=got,
            resource=resource,
        )
