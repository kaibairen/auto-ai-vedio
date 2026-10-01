"""ToolAdapter protocol (ENG N4 adapter boundary)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aiv_drama_n4.skeleton import DIR_SLOT_ORDER, join_slots


@dataclass
class ToolAdapter:
    profile_id: str
    aliases: tuple[str, ...] = ()
    max_prompt_len: int = 800
    allowed_durations: frozenset[int] = field(default_factory=lambda: frozenset({5, 8, 10}))
    allowed_aspects: frozenset[str] = field(default_factory=lambda: frozenset({"9:16", "16:9", "2.35:1"}))
    max_ref_images: int = 9
    default_aspect: str = "9:16"

    @property
    def name(self) -> str:
        return self.profile_id

    def matches(self, raw: str) -> bool:
        key = (raw or "").strip()
        return key == self.profile_id or key in self.aliases or key.lower() in {a.lower() for a in self.aliases}

    def format_negative(self, core: str, extra: str = "") -> str:
        parts = [str(core or "").strip()]
        extra_text = str(extra or "").strip()
        if extra_text:
            parts.append(extra_text)
        return "，".join(p for p in parts if p)

    def normalize_camera(self, code: str | None, *, notes: str | None = None) -> str:
        from aiv_drama_n4.camera import camera_lex

        return camera_lex(code, notes=notes)

    def format_prompt(self, parts: dict[str, Any], *, extra_tail: str | None = None) -> str:
        trimmed = self._drop_optional(parts, extra_tail=extra_tail)
        return join_slots(trimmed["parts"], extra_tail=trimmed["extra_tail"])

    def _drop_optional(self, parts: dict[str, Any], *, extra_tail: str | None) -> dict[str, Any]:
        """If over max_prompt_len, drop style/duration/micro/light first. Never cut features or camera."""
        working = {key: parts.get(key) for key in DIR_SLOT_ORDER}
        tail = extra_tail
        optional = (
            "slot_duration_hint",
            "slot_micro_expr",
            "slot_light_mood",
            "slot_ref_lead",
        )
        text = join_slots(working, extra_tail=tail)
        if len(text) <= self.max_prompt_len:
            return {"parts": working, "extra_tail": tail}
        tail = None
        text = join_slots(working, extra_tail=None)
        if len(text) <= self.max_prompt_len:
            return {"parts": working, "extra_tail": None}
        for key in optional:
            if not working.get(key):
                continue
            working[key] = ""
            text = join_slots(working, extra_tail=None)
            if len(text) <= self.max_prompt_len:
                return {"parts": working, "extra_tail": None}
        return {"parts": working, "extra_tail": None}
