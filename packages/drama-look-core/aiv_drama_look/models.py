from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


LookProviderName = Literal["auto", "ark", "seedream", "dashscope", "wan"]
UpgradeReason = Literal["identity_drift", "api_fail", "quality_gate"]
LookView = Literal["front", "side", "three_quarter", "empty", "ls"]
LookRole = Literal["face", "full", "plate", "look", "style_ref", "web_source"]


class LookGenerateRequest(BaseModel):
    """Generate one look still for a thickened CHAR/SCENE card. extra=forbid."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1)
    actor: str | None = None
    provider: LookProviderName | None = "auto"
    sku: str | None = None
    view: LookView | None = None
    role: LookRole | None = None
    style_ref: str | None = None
    unlock_edit: bool = False
    upgrade_reason: UpgradeReason | None = None
    watermark: bool | None = False
    seed: int | None = Field(default=None, ge=0, le=2147483647)
