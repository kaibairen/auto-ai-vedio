"""Tool-profile adapter registry.

BRIEF alias `seedance_2_0` persists as closed-set `seedance_2`.
The registry shell can grow; this shot ships only Seedance 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiv_drama.errors import AppError
from aiv_schema.models import NODE_DN4

CANONICAL_SEEDANCE = "seedance_2"
SHIPPED_PROFILES = frozenset({CANONICAL_SEEDANCE})

# BRIEF / colloquial aliases → persist name (仓内闭集).
SEEDANCE_ALIASES = (
    "seedance_2",
    "seedance_2_0",
    "seedance_2.0",
    "seedance2.0",
    "seedance2",
    "Seedance2.0",
    "SEEDANCE_2_0",
    "SEEDANCE_2",
)


@dataclass(frozen=True)
class ToolAdapter:
    name: str
    aliases: tuple[str, ...]
    default_aspect: str = "9:16"

    def matches(self, raw: str) -> bool:
        key = (raw or "").strip()
        return key == self.name or key in self.aliases


class Seedance2Adapter(ToolAdapter):
    def __init__(self) -> None:
        super().__init__(name=CANONICAL_SEEDANCE, aliases=SEEDANCE_ALIASES, default_aspect="9:16")


_REGISTRY: dict[str, ToolAdapter] = {}


def register_adapter(adapter: ToolAdapter) -> None:
    """Extensible shell. Duplicate persist-name overwrites aliases only."""
    _REGISTRY[adapter.name] = adapter
    for alias in adapter.aliases:
        _REGISTRY[alias] = adapter
        _REGISTRY[alias.lower()] = adapter


def shipped_adapters() -> dict[str, ToolAdapter]:
    return {name: adapter for name, adapter in _REGISTRY.items() if adapter.name in SHIPPED_PROFILES}


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
        return adapter.name, None
    adapter = lookup_adapter(original)
    if adapter is None or adapter.name not in SHIPPED_PROFILES:
        raise AppError(
            422,
            "unsupported_tool_profile",
            "本拍工具闭集只落盘 seedance_2（入参别名 seedance_2_0 可接受）",
            node=NODE_DN4,
            tool_profile_input=original,
            shipped=sorted(SHIPPED_PROFILES),
        )
    return adapter.name, original


def adapter_observability() -> dict[str, Any]:
    return {
        "shipped": sorted(SHIPPED_PROFILES),
        "aliases": {CANONICAL_SEEDANCE: list(SEEDANCE_ALIASES)},
        "persist_as": CANONICAL_SEEDANCE,
        "note": "壳可 register_adapter；本拍只交 seedance_2",
    }


register_adapter(Seedance2Adapter())
