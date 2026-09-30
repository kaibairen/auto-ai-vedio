from __future__ import annotations

from typing import Any

from aiv_drama.config import Settings
from aiv_drama.errors import AppError
from aiv_drama_n2.provider.fixture import FixtureStoryboardProvider


def get_storyboard_provider(name: str | None, settings: Settings) -> FixtureStoryboardProvider:
    chosen = (name or settings.default_provider or "fixture").strip().lower()
    if chosen in {"openai", "openai_compat", "llm"}:
        if not settings.openai_api_key:
            raise AppError(422, "provider", "llm provider requires AIV_OPENAI_API_KEY; use fixture")
        # Fixture LLM is the supported no-key path; live LLM is out of D-N2 dogfood.
        return FixtureStoryboardProvider(settings)
    if chosen in {"fixture", "skill"}:
        return FixtureStoryboardProvider(settings)
    raise AppError(422, "validation", "provider must be fixture|llm|skill", provider=chosen)


def generate_rows(
    settings: Settings,
    *,
    provider: str | None,
    outline: dict[str, Any],
    cast: dict[str, Any],
    shot_cap: int,
    tool_profile: str | None,
    episode_id: str,
) -> list[dict[str, Any]]:
    return get_storyboard_provider(provider, settings).generate(
        episode_id=episode_id,
        outline=outline,
        cast=cast,
        shot_cap=shot_cap,
        tool_profile=tool_profile,
    )
