"""First-ship Seedance 2 adapter. BRIEF alias seedance_2_0 → persist seedance_2."""

from __future__ import annotations

from aiv_drama_n4.adapters.base import ToolAdapter

CANONICAL_SEEDANCE = "seedance_2"
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


class Seedance2Adapter(ToolAdapter):
    def __init__(self) -> None:
        super().__init__(
            profile_id=CANONICAL_SEEDANCE,
            aliases=SEEDANCE_ALIASES,
            max_prompt_len=800,
            allowed_durations=frozenset({5, 8, 10}),
            allowed_aspects=frozenset({"9:16", "16:9", "2.35:1"}),
            max_ref_images=9,
            default_aspect="9:16",
        )
