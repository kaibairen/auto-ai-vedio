from __future__ import annotations

from typing import Any, Protocol

from aiv_drama.models import GeneratedDraft


class OutlineProvider(Protocol):
    name: str

    def generate(
        self,
        *,
        episode_id: str,
        lane: str,
        shot_cap: int,
        brief: dict[str, Any],
    ) -> GeneratedDraft: ...
