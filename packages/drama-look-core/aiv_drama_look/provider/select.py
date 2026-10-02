"""Pick Ark / DashScope from env. Never fall back to AIV_OPENAI_API_KEY."""

from __future__ import annotations

from aiv_drama.config import Settings
from aiv_drama.errors import AppError
from aiv_drama_look.provider.ark import ArkSeedreamClient
from aiv_drama_look.provider.base import ImageProvider
from aiv_drama_look.provider.dashscope import DashScopeWanClient
from aiv_drama_look.sku import provider_family
from aiv_schema.models import NODE_DN3

ISOLATED_ALIASES = frozenset({"openai", "llm", "deepseek", "openai_compat", "fixture"})


def build_image_provider(
    settings: Settings,
    name: str | None,
    *,
    sku: str | None = None,
) -> ImageProvider:
    chosen = (name or "auto").strip().lower()
    if chosen in ISOLATED_ALIASES:
        raise AppError(
            422,
            "provider",
            "Look clients are isolated from AIV_OPENAI_API_KEY/DeepSeek; use ark|dashscope|auto",
            node=NODE_DN3,
            provider=chosen,
        )
    family = provider_family(sku) if sku else None
    if chosen == "auto":
        if family == "dashscope":
            return DashScopeWanClient(settings)
        if getattr(settings, "ark_api_key", None):
            return ArkSeedreamClient(settings)
        if getattr(settings, "dashscope_api_key", None):
            return DashScopeWanClient(settings)
        raise AppError(
            422,
            "provider",
            "Look requires ARK_API_KEY or DASHSCOPE_API_KEY (not AIV_OPENAI_API_KEY)",
            node=NODE_DN3,
        )
    if chosen in {"ark", "seedream"}:
        return ArkSeedreamClient(settings)
    if chosen in {"dashscope", "wan"}:
        return DashScopeWanClient(settings)
    raise AppError(422, "provider", f"unknown look provider {chosen}", node=NODE_DN3, provider=chosen)
