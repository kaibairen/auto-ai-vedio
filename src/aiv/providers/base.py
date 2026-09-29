from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class GenerateRequest:
    path: str
    step: int
    kind: str
    raw: str
    notes: str = ""
    analysis: dict[str, Any] | None = None
    frameworks: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    pick: int | None = None
    title: str | None = None
    prompt_text: str = ""
    prompt_relpath: str = ""


@dataclass
class GenerateResponse:
    kind: str
    message: str
    analysis: dict[str, Any] | None = None
    frameworks: list[str] | None = None
    candidates: list[dict[str, Any]] | None = None
    titles: list[str] | None = None
    draft_title: str | None = None
    draft_body: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str

    def generate(self, req: GenerateRequest) -> GenerateResponse: ...
