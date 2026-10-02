"""ENG hook only — live Seedream/wan clients live in drama-look-core.

Key isolation (do not reuse DeepSeek / AIV_OPENAI_API_KEY):
  ARK_API_KEY          — Ark Seedream (images/generations)
  DASHSCOPE_API_KEY    — DashScope wan (multimodal-generation)

BE attach-ref mounts local fixtures into the looks tree.
Real generate is aiv_drama_look.provider.select.build_image_provider
+ aiv_drama_look.ops.DramaLookOps.generate_look. This module stays a hook
so BE tests never import live clients.
"""

from __future__ import annotations

from typing import Any


def generate_look(*_args: Any, **_kwargs: Any) -> list[str]:
    raise RuntimeError(
        "AIV-031: live Seedream/wan is in drama-look-core; this hook is not the generate path"
    )
