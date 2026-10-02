"""ImageProvider contract. DESIGN-AIV-031-ENG §5. Isolated from AIV_OPENAI_*."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

DEFAULT_ASPECT = "9:16"
DEFAULT_SIZE = "1440x2560"  # 9:16 · frozen with N4/N5 口径


@dataclass(frozen=True)
class FrozenParams:
    size: str = DEFAULT_SIZE
    aspect: str = DEFAULT_ASPECT
    watermark: bool = False
    sequential_image_generation: str = "disabled"
    enable_sequential: bool = False
    n: int = 1
    response_format: str = "b64_json"
    output_format: str = "png"

    def as_dict(self) -> dict[str, Any]:
        return {
            "size": self.size,
            "aspect": self.aspect,
            "watermark": self.watermark,
            "sequential_image_generation": self.sequential_image_generation,
            "enable_sequential": self.enable_sequential,
            "n": self.n,
            "response_format": self.response_format,
            "output_format": self.output_format,
        }


def default_frozen_params(*, watermark: bool = False) -> FrozenParams:
    return FrozenParams(watermark=False if watermark is not True else False)


@dataclass
class ImageResult:
    images: list[bytes]
    sku: str
    provider: str
    seed: int | None = None
    seed_replay: str = "ok"  # ok | partial
    classified_error: str | None = None
    raw_urls: list[str] = field(default_factory=list)


class ImageProvider(Protocol):
    name: str
    supports_sequential: bool
    max_refs: int

    def generate(
        self,
        prompt: str,
        refs: list[dict[str, Any]],
        frozen_params: FrozenParams,
        seed: int | None = None,
        *,
        sku: str | None = None,
    ) -> ImageResult: ...
