from __future__ import annotations

from pydantic import BaseModel, Field


class N5bSubmitRequest(BaseModel):
    model_config = {"extra": "forbid"}

    actor: str | None = None
    shot: str | None = Field(default=None, description="Optional shot_id filter")
    model: str | None = None


class N5bGateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    decision: str | None = None
    verdict: str | None = None
    actor: str | None = None
    note: str | None = None
