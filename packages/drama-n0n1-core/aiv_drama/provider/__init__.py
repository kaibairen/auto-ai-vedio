from __future__ import annotations

from aiv_drama.config import Settings
from aiv_drama.errors import AppError
from aiv_drama.provider.base import OutlineProvider
from aiv_drama.provider.fixture import FixtureProvider
from aiv_drama.provider.llm import LlmProvider


def get_provider(name: str | None, settings: Settings) -> OutlineProvider:
    chosen = (name or settings.default_provider or "fixture").strip().lower()
    if chosen in {"openai", "openai_compat"}:
        chosen = "llm"
    if chosen == "fixture":
        return FixtureProvider(settings)
    if chosen == "llm":
        return LlmProvider(settings)
    raise AppError(422, "validation", "provider must be fixture|llm", provider=chosen)
