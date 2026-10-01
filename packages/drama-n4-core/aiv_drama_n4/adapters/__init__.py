"""N4 tool adapter registry. This shot ships only seedance_2."""

from __future__ import annotations

from typing import Any

from aiv_drama.errors import AppError
from aiv_drama_n4.adapters.base import ToolAdapter
from aiv_drama_n4.adapters.seedance_2 import CANONICAL_SEEDANCE, SEEDANCE_ALIASES, Seedance2Adapter
from aiv_schema.models import NODE_DN4

SHIPPED_PROFILES = frozenset({CANONICAL_SEEDANCE})

_REGISTRY: dict[str, ToolAdapter] = {}


def register_adapter(adapter: ToolAdapter) -> None:
    _REGISTRY[adapter.profile_id] = adapter
    for alias in adapter.aliases:
        _REGISTRY[alias] = adapter
        _REGISTRY[alias.lower()] = adapter


def shipped_adapters() -> dict[str, ToolAdapter]:
    return {name: adapter for name, adapter in _REGISTRY.items() if adapter.profile_id in SHIPPED_PROFILES}


def lookup_adapter(raw: str | None) -> ToolAdapter | None:
    if raw is None:
        return None
    key = raw.strip()
    if not key:
        return None
    return _REGISTRY.get(key) or _REGISTRY.get(key.lower())


def normalize_tool_profile(raw: str | None, *, default: str | None = CANONICAL_SEEDANCE) -> tuple[str, str | None]:
    """Return (persist_name, original_input). Rejects unshipped profiles."""
    original = (raw or "").strip() or None
    if not original:
        if not default:
            raise AppError(
                422,
                "unsupported_tool_profile",
                "本拍只交付 seedance_2；请显式选择或使用 seedance_2_0 别名",
                node=NODE_DN4,
                shipped=sorted(SHIPPED_PROFILES),
            )
        adapter = lookup_adapter(default)
        if adapter is None:
            raise AppError(422, "unsupported_tool_profile", "unknown default tool_profile", node=NODE_DN4)
        return adapter.profile_id, None
    adapter = lookup_adapter(original)
    if adapter is None or adapter.profile_id not in SHIPPED_PROFILES:
        raise AppError(
            422,
            "unsupported_tool_profile",
            "本拍工具闭集只落盘 seedance_2（入参别名 seedance_2_0 可接受）",
            node=NODE_DN4,
            tool_profile_input=original,
            shipped=sorted(SHIPPED_PROFILES),
        )
    return adapter.profile_id, original


def adapter_observability() -> dict[str, Any]:
    return {
        "shipped": sorted(SHIPPED_PROFILES),
        "aliases": {CANONICAL_SEEDANCE: list(SEEDANCE_ALIASES)},
        "persist_as": CANONICAL_SEEDANCE,
        "max_prompt_len": Seedance2Adapter().max_prompt_len,
        "allowed_durations": sorted(Seedance2Adapter().allowed_durations),
        "allowed_aspects": sorted(Seedance2Adapter().allowed_aspects),
        "max_ref_images": Seedance2Adapter().max_ref_images,
        "note": "壳可 register_adapter；本拍只交 seedance_2",
    }


register_adapter(Seedance2Adapter())

__all__ = [
    "CANONICAL_SEEDANCE",
    "SEEDANCE_ALIASES",
    "SHIPPED_PROFILES",
    "Seedance2Adapter",
    "ToolAdapter",
    "adapter_observability",
    "lookup_adapter",
    "normalize_tool_profile",
    "register_adapter",
    "shipped_adapters",
]
