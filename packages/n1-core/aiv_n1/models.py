from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PathId = Literal["A", "B"]
ProviderName = Literal["fixture", "openai_compat", "openai"]


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: PathId = "A"
    provider: ProviderName = "fixture"
    source_ref: str | None = None
    reset: bool = False
    actor: str | None = None


class EpisodeCreate(BaseModel):
    ep: str = "EP01"
    title: str | None = None


class DraftPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = ""
    body: str = ""
    markdown: str | None = None
    framework: str | None = None
    actor: str | None = None


class StepSubmit(BaseModel):
    """BE §2.3. Unknown fields → 422."""

    model_config = ConfigDict(extra="forbid")
    raw_text: str | None = None
    text: str | None = None
    decision: str | None = None
    confirm: bool | None = None
    frameworks: list[str] | None = None
    framework: str | None = None
    candidate_id: str | None = None
    pick: int | None = None
    title_id: str | None = None
    title: str | None = None
    ack_defect: bool | None = None
    ack_source_gap: bool | None = None
    human_revised_frameworks: bool | None = None
    manual_revised: bool | None = None
    notes: str | None = None
    edits: dict[str, Any] | None = None
    actor: str | None = None


def next_edges_after_g1() -> list[dict[str, Any]]:
    # provisional:P-D2 — candidates only; do not enqueue writer.
    return [
        {
            "to": "writer",
            "gate": "g1b",
            "requires": ["pipeline_profile"],
            "provisional": True,
        },
        {
            "to": "n2",
            "gate": "g2",
            "requires": ["pipeline_profile=koubo"],
            "provisional": True,
        },
    ]
