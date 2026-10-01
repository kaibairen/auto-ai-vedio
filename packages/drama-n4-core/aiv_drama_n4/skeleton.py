"""DIR skeleton slot order. Deterministic fill — not an LLM writer.

Slot order follows KEEP Seedance 核心公式 (DESIGN DIR 未挂载时的仓内权威):
风格 → 主体 → 场景 → 动作 → 镜头 → 光影 → (对白).
"""

from __future__ import annotations

SKELETON_ID = "dir-seedance-v0"
SKELETON_VERSION = 1

# Ordered slot ids. dialogue is omitted when empty.
SKELETON_SLOTS: tuple[str, ...] = (
    "style",
    "subject",
    "scene",
    "action",
    "camera",
    "light",
    "dialogue",
)

SLOT_LABELS: dict[str, str] = {
    "style": "【风格】",
    "subject": "【主体】",
    "scene": "【场景】",
    "action": "【动作】",
    "camera": "【镜头】",
    "light": "【光影】",
    "dialogue": "【对白】",
}

DEFAULT_STYLE = "电影级写实风格"
DEFAULT_LIGHT = "平光，环境光稳定"
EMPTY_SUBJECT = "空镜，无具名角色"
EMPTY_SCENE = "未指定场景"


def render_slots(filled: dict[str, str]) -> str:
    """Join filled slots in DIR order. Skip empty optional slots."""
    parts: list[str] = []
    for slot in SKELETON_SLOTS:
        value = (filled.get(slot) or "").strip()
        if not value:
            continue
        if slot == "dialogue" and not value:
            continue
        label = SLOT_LABELS[slot]
        if value.startswith(label):
            parts.append(value)
        else:
            parts.append(f"{label}{value}")
    return "\n".join(parts)
