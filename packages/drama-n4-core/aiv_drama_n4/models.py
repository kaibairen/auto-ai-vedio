from __future__ import annotations

from pydantic import BaseModel, Field


class N4AssembleRequest(BaseModel):
    model_config = {"extra": "forbid"}

    actor: str | None = None
    tool_profile: str | None = None
    aspect: str | None = None
    unlock_edit: bool = False


class N4ValidateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    actor: str | None = None
    tool_profile: str | None = None
    aspect: str | None = None
