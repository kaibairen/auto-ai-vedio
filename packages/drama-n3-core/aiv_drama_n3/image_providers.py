"""ENG hook — live image clients are OUT of BE scope (AIV-031).

Key isolation (do not reuse DeepSeek / AIV_OPENAI_API_KEY):
  ARK_API_KEY          — Ark Seedream (images/generations)
  DASHSCOPE_API_KEY    — DashScope wan (multimodal-generation)

TODO(ENG): ImageProvider.generate + Seedream/wan dogfood. BE attach-ref
only mounts local fixtures into the looks tree.
"""

from __future__ import annotations

from typing import Any


def generate_look(*_args: Any, **_kwargs: Any) -> list[str]:
    raise RuntimeError("AIV-031-ENG: live Seedream/wan generation is out of BE scope")
