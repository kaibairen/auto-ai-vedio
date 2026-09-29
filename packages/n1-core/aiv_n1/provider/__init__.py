from __future__ import annotations

from aiv_n1.config import Settings
from aiv_n1.provider.base import LlmProvider
from aiv_n1.provider.fixture import FixtureProvider
from aiv_n1.provider.openai_compat import OpenAICompatProvider


def get_provider(name: str, settings: Settings) -> LlmProvider:
    key = (name or settings.default_provider or "fixture").strip().lower()
    if key in {"openai", "openai_compat"}:
        if not settings.openai_api_key:
            return FixtureProvider()
        return OpenAICompatProvider(settings)
    return FixtureProvider()
