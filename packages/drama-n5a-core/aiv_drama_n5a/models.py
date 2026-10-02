from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

G4Verdict = Literal["pass", "rework"]


class N5aGenerateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    actor: str | None = None
    layout: int = 9
    shots: list[str] = Field(default_factory=list)
    dry_run: bool = False


class N5aGateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    actor: str
    verdict: G4Verdict
    note: str | None = None
