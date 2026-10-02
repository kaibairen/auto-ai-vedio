"""CU/LS prompt assembly from card fields + Skill defaults. No episode-specific ForcePass prose."""

from __future__ import annotations

import hashlib
from typing import Any

from aiv_drama.errors import AppError
from aiv_drama_n3.thicken import HOLLOW_APPEARANCE, HOLLOW_LIGHT, as_string_list
from aiv_schema.models import NODE_DN3

# DESIGN-AIV-031-LOOK §3 STYLE-REF default (configurable whole-sentence replace).
DEFAULT_STYLE_REF = (
    "统一画风：二次元赛璐璐棚拍定妆，干净边缘，柔和赛璐璐上色，细腻皮肤与布料质感，竖屏构图，定妆棚拍质感。"
)

# Skill 11-slot defaults (CAM/LEARN). Not persisted as WorkingCard keys.
CHAR_CU_DEFAULTS = {
    "SHOT": "近景，胸以上，脸为主锚",
    "ORIENT": "正面平视",
    "LIGHT": "柔和正面主光，弱补光，中性棚光",
    "FRAMING": "居中，干净底",
    "SAFE": "面部安全区完整，勿裁切眼眉颏",
    "EXPR": "中性表情",
}

SCENE_LS_DEFAULTS = {
    "SHOT": "全景空镜",
    "FRAMING": "中心 60% 空间锚",
    "EMPTY": "空镜，无角色入画",
    "NO_SIGNAGE": "禁可读招牌、禁 UI、禁字幕",
}

CHAR_NEGATIVES = "no readable text, no logo, no watermark, 禁字，禁水印，禁商标"
SCENE_NEGATIVES = "no readable signage, no logo, no UI, no watermark, 禁可读招牌"


def _nonempty(text: Any) -> str:
    return str(text or "").strip()


def _is_hollow(text: Any, hollow: frozenset[str]) -> bool:
    value = _nonempty(text)
    return (not value) or value in hollow


def resolve_style_ref(override: str | None, settings_style: str | None = None) -> str:
    for candidate in (override, settings_style):
        if _nonempty(candidate):
            return _nonempty(candidate)
    return DEFAULT_STYLE_REF


def require_look_must(card: dict[str, Any]) -> None:
    kind = card.get("kind")
    ident = card.get("id")
    issues: list[dict[str, Any]] = []
    if kind == "character":
        if _is_hollow(card.get("appearance"), HOLLOW_APPEARANCE):
            issues.append({"id": ident, "field": "appearance", "kind": kind})
        if not as_string_list(card.get("immutable")):
            issues.append({"id": ident, "field": "immutable", "kind": kind})
    elif kind == "scene":
        if _is_hollow(card.get("appearance"), HOLLOW_APPEARANCE):
            issues.append({"id": ident, "field": "appearance", "kind": kind})
        if _is_hollow(card.get("light_anchor"), HOLLOW_LIGHT):
            issues.append({"id": ident, "field": "light_anchor", "kind": kind})
    else:
        issues.append({"id": ident, "field": "kind", "kind": kind})
    if issues:
        raise AppError(
            422,
            "look_incomplete",
            "出图前 MUST 仍空（CHAR appearance+immutable / SCENE appearance+light_anchor）",
            issues=issues,
            node=NODE_DN3,
        )


def _orient_for_view(view: str) -> str:
    mapping = {
        "front": "正面平视",
        "side": "侧面平视",
        "three_quarter": "四分之三侧面",
        "empty": "空镜，无角色朝向",
        "ls": "全景空镜",
    }
    return mapping.get(view, CHAR_CU_DEFAULTS["ORIENT"])


def assemble_look_prompt(
    card: dict[str, Any],
    *,
    view: str,
    style_ref: str | None = None,
    settings_style: str | None = None,
) -> dict[str, Any]:
    """Map appearance/immutable/light_anchor + Skill defaults. No invented episode prose."""
    require_look_must(card)
    kind = card.get("kind")
    style = resolve_style_ref(style_ref, settings_style)
    appearance = _nonempty(card.get("appearance"))
    immutable = as_string_list(card.get("immutable"))
    light_anchor = _nonempty(card.get("light_anchor"))
    slots: dict[str, str] = {"STYLE_LOCK": style, "IDENTITY": appearance}

    if kind == "character":
        slots["IMMUTABLE"] = "；".join(immutable)
        light = CHAR_CU_DEFAULTS["LIGHT"]
        if light_anchor and light_anchor not in light:
            light = f"{light}（戏光备注：{light_anchor}）"
        slots["LIGHT"] = light
        slots["SHOT"] = CHAR_CU_DEFAULTS["SHOT"]
        slots["ORIENT"] = _orient_for_view(view)
        slots["FRAMING"] = CHAR_CU_DEFAULTS["FRAMING"]
        slots["SAFE_ZONE"] = CHAR_CU_DEFAULTS["SAFE"]
        slots["EXPR_BOUND"] = CHAR_CU_DEFAULTS["EXPR"]
        slots["NEGATIVES"] = CHAR_NEGATIVES
        order = (
            "STYLE_LOCK",
            "IDENTITY",
            "IMMUTABLE",
            "LIGHT",
            "SHOT",
            "ORIENT",
            "FRAMING",
            "SAFE_ZONE",
            "EXPR_BOUND",
            "NEGATIVES",
        )
    else:
        slots["IMMUTABLE"] = "；".join(immutable) if immutable else ""
        slots["LIGHT"] = light_anchor
        slots["SHOT"] = SCENE_LS_DEFAULTS["SHOT"]
        slots["FRAMING"] = SCENE_LS_DEFAULTS["FRAMING"]
        slots["LS_EMPTY"] = SCENE_LS_DEFAULTS["EMPTY"]
        slots["NO_SIGNAGE"] = SCENE_LS_DEFAULTS["NO_SIGNAGE"]
        slots["NEGATIVES"] = SCENE_NEGATIVES
        order = (
            "STYLE_LOCK",
            "IDENTITY",
            "IMMUTABLE",
            "LIGHT",
            "SHOT",
            "FRAMING",
            "LS_EMPTY",
            "NO_SIGNAGE",
            "NEGATIVES",
        )

    parts = [slots[key] for key in order if slots.get(key)]
    prompt = "，".join(parts)
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return {
        "prompt": prompt,
        "slots": slots,
        "slot_order": list(order),
        "style_ref": style,
        "prompt_hash": digest,
        "view": view,
        "kind": kind,
        "card_id": card.get("id"),
    }
