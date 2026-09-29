from __future__ import annotations

from aiv.config import Settings
from aiv.providers.base import LLMProvider
from aiv.providers.fixture import FixtureProvider
from aiv.providers.openai_compat import OpenAICompatProvider


def get_provider(name: str, settings: Settings) -> LLMProvider:
    key = (name or settings.default_provider or "fixture").strip().lower()
    if key == "openai":
        if not settings.openai_api_key:
            return FixtureProvider()
        return OpenAICompatProvider(settings)
    return FixtureProvider()
