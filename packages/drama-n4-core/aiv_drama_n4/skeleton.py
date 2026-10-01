"""DIR N4 skeleton: slot names + join_nonempty. Deterministic fill — not LLM.

SoT: DESIGN-026-DIR-N4-SKELETON-v0.
prompt = join_nonempty([...], sep="。")
Dialogue is not forced into the prompt (avoids burned-in subtitles).
Light is omitted when the card/notes have none — never invent 平光.
"""

from __future__ import annotations

from typing import Any, Iterable

SKELETON_ID = "dir-n4-skeleton-v0"
SKELETON_VERSION = 2

SLOT_REF_LEAD = "以参考图为主体，保风格与空间相对位置"

# Frozen DIR slot order (machine names).
DIR_SLOT_ORDER: tuple[str, ...] = (
    "slot_ref_lead",
    "slot_subject_blocks",
    "slot_scene_anchor",
    "slot_light_mood",
    "slot_action",
    "slot_micro_expr",
    "slot_shot_size_lex",
    "slot_camera_lex",
    "slot_duration_hint",
)

# Historical names kept so existing imports do not explode.
SKELETON_SLOTS = DIR_SLOT_ORDER
SLOT_LABELS: dict[str, str] = {}

EMPTY_SUBJECT = "空镜，无具名角色"
EMPTY_SCENE = ""


def _slot_text(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return "；".join(_slot_text(item) for item in value if _slot_text(item))
    return " ".join(str(value or "").split()).strip().strip("。；,，").strip()


def join_nonempty(parts: Iterable[Any], *, sep: str = "。") -> str:
    cleaned = [text for text in (_slot_text(part) for part in parts) if text]
    if not cleaned:
        return ""
    joined = sep.join(cleaned)
    if not joined.endswith("。"):
        joined += "。"
    return joined


def join_slots(filled: dict[str, Any], *, extra_tail: str | None = None) -> str:
    values = [filled.get(slot) for slot in DIR_SLOT_ORDER]
    if extra_tail:
        values.append(extra_tail)
    return join_nonempty(values, sep="。")


def render_slots(filled: dict[str, Any]) -> str:
    """DIR formula. Accepts either DIR slot names or a short alias map."""
    aliases = {
        "style": "slot_ref_lead",
        "subject": "slot_subject_blocks",
        "scene": "slot_scene_anchor",
        "light": "slot_light_mood",
        "action": "slot_action",
        "micro": "slot_micro_expr",
        "shot_size": "slot_shot_size_lex",
        "camera": "slot_camera_lex",
        "duration": "slot_duration_hint",
    }
    mapped: dict[str, Any] = dict(filled)
    for old, new in aliases.items():
        if old in filled and new not in mapped:
            mapped[new] = filled[old]
    return join_slots(mapped)
