"""Tool-profile adapter registry facade.

BRIEF alias `seedance_2_0` persists as closed-set `seedance_2`.
"""

from __future__ import annotations

from aiv_drama_n4.adapters import (
    CANONICAL_SEEDANCE,
    SEEDANCE_ALIASES,
    SHIPPED_PROFILES,
    Seedance2Adapter,
    ToolAdapter,
    adapter_observability,
    lookup_adapter,
    normalize_tool_profile,
    register_adapter,
    shipped_adapters,
)

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
