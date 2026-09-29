from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

PathId = Literal["A", "B"]
Decision = Literal["pass", "reject"]
Consumer = Literal["authoring", "downstream"]
ProviderName = Literal["fixture", "openai"]


class Framework(BaseModel):
    id: str
    name: str
    summary: str
    defective: bool = False


class StepSpec(BaseModel):
    step: int
    kind: str
    label: str
    accepts: list[str]
    skipped: bool = False
    skip_reason: str | None = None
    char_limit: int | None = None
    frameworks: list[Framework] | None = None


class Candidate(BaseModel):
    index: int
    title: str
    body: str
    chars: int
    framework: str = ""


class DraftPayload(BaseModel):
    title: str = ""
    body: str = ""
    markdown: str | None = None
    framework: str | None = None
    actor: str | None = None


class SubmitPayload(BaseModel):
    text: str = ""
    confirm: bool = True
    notes: str = ""
    frameworks: list[str] = Field(default_factory=list)
    pick: int | None = None
    title: str | None = None
    actor: str | None = None


class SessionCreate(BaseModel):
    path: PathId = "A"
    provider: ProviderName = "fixture"
    source_ref: str | None = None
    actor: str | None = None


class EpisodeCreate(BaseModel):
    ep: str = "EP01"
    title: str | None = None


class GateConfirm(BaseModel):
    decision: Decision
    actor: str = ""
    notes: str = ""
    artifact_version: int | None = None
    rollback_to: int | None = None
    force_pass: Any | None = None


class NextEdge(BaseModel):
    id: str
    label: str
    gate: str | None = None
    requires_decision: str | None = None
    status: str
    reason: str


def next_edges_after_g1() -> list[NextEdge]:
    """D2 unset: expose candidates only. Do not auto-advance to 编剧."""
    reason = (
        "D2 unset and pipeline_profile missing; N1 does not guess the next node "
        "(provisional D2: no auto-advance to 编剧)"
    )
    return [
        NextEdge(
            id="writer",
            label="编剧扩场",
            gate="g1b",
            requires_decision="D2",
            status="blocked",
            reason=reason,
        ),
        NextEdge(
            id="n2",
            label="N2 分镜",
            gate="g2",
            requires_decision="D2",
            status="blocked",
            reason="only valid if D2-B (koubo skip writer); not guessed",
        ),
    ]
