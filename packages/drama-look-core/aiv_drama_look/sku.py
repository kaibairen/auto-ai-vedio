"""SKU ladder + upgrade hooks. DESIGN-AIV-031-ENG §4 / LOOK §6. ≠更好看."""

from __future__ import annotations

from typing import Any

from aiv_drama.errors import AppError
from aiv_schema.models import NODE_DN3

SKU_L0 = "doubao-seedream-5-0-flash-260915"
SKU_L1 = "doubao-seedream-5-0-pro-260628"
SKU_L2 = "doubao-seedream-4-5-251128"
SKU_F0 = "wan2.7-image"
SKU_F1 = "wan2.7-image-pro"

DEFAULT_SKU = SKU_L0

LADDER: tuple[tuple[str, str, str], ...] = (
    ("L0", SKU_L0, "ark"),
    ("L1", SKU_L1, "ark"),
    ("L2", SKU_L2, "ark"),
    ("F0", SKU_F0, "dashscope"),
    ("F1", SKU_F1, "dashscope"),
)

UPGRADE_REASONS = frozenset({"identity_drift", "api_fail", "quality_gate"})
FORBIDDEN_UPGRADE_REASONS = frozenset({"prettier", "better_look", "aesthetic", "更好看", "好看"})

MAX_DRAWS_PER_CARD = 5
MAX_DRAWS_PER_EPISODE = 32
FLASH_UNIT_CNY = 0.12


def ladder_row(sku: str) -> tuple[str, str, str] | None:
    for row in LADDER:
        if row[1] == sku:
            return row
    return None


def provider_family(sku: str) -> str:
    row = ladder_row(sku)
    if row:
        return row[2]
    if (sku or "").startswith("wan"):
        return "dashscope"
    return "ark"


def next_sku(current: str | None) -> str:
    """Scheme hook: L0→L1→L2→F0→F1. Last rung stays (caller must stop / 改卡)."""
    cur = current or DEFAULT_SKU
    for idx, row in enumerate(LADDER):
        if row[1] == cur:
            if idx + 1 < len(LADDER):
                return LADDER[idx + 1][1]
            return cur
    return SKU_L1 if provider_family(cur) == "ark" else SKU_F1


def reject_upgrade_reason(reason: str | None) -> str | None:
    if reason is None or reason == "":
        return None
    text = reason.strip()
    if text in FORBIDDEN_UPGRADE_REASONS:
        raise AppError(
            422,
            "validation",
            "升档≠更好看；reason 须为 identity_drift|api_fail|quality_gate",
            reason=text,
            node=NODE_DN3,
        )
    if text not in UPGRADE_REASONS:
        raise AppError(
            422,
            "validation",
            "升档 reason 须为 identity_drift|api_fail|quality_gate",
            reason=text,
            node=NODE_DN3,
        )
    return text


def resolve_sku(
    requested: str | None,
    *,
    settings_sku: str | None,
    current_sku: str | None = None,
    upgrade_reason: str | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Return (sku, upgrade_meta|None). Does not auto-loop."""
    reason = reject_upgrade_reason(upgrade_reason)
    base = (requested or settings_sku or current_sku or DEFAULT_SKU).strip()
    if reason and not requested:
        nxt = next_sku(current_sku or settings_sku or DEFAULT_SKU)
        meta = {"sku_from": current_sku or settings_sku or DEFAULT_SKU, "sku_to": nxt, "reason": reason}
        return nxt, meta
    if reason and requested:
        return requested.strip(), {
            "sku_from": current_sku or settings_sku or DEFAULT_SKU,
            "sku_to": requested.strip(),
            "reason": reason,
        }
    return base, None
