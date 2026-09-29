from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class GenerateRequest:
    path: str
    step: str
    kind: str
    raw: str
    notes: str = ""
    extract: dict[str, Any] | None = None
    frameworks: list[str] = field(default_factory=list)
    titles: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    candidate_id: str | None = None
    title: str | None = None
    prompt_text: str = ""


@dataclass
class GenerateResponse:
    kind: str
    message: str
    extract: dict[str, Any] | None = None
    frameworks: list[str] | None = None
    candidates: list[dict[str, Any]] | None = None
    titles: list[dict[str, Any]] | None = None
    draft_title: str | None = None
    draft_body: str | None = None


class LlmProvider(Protocol):
    name: str

    def generate(self, req: GenerateRequest) -> GenerateResponse: ...
