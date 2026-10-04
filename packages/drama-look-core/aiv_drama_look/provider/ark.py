"""Ark Seedream · POST {base}/images/generations · ARK_API_KEY only."""

from __future__ import annotations

from typing import Any

import httpx

from aiv_drama.config import Settings
from aiv_drama.errors import AppError
from aiv_drama_look.provider.base import FrozenParams, ImageResult
from aiv_drama_look.provider.errors import decode_b64_image, look_provider_error
from aiv_drama_look.sku import DEFAULT_SKU, SKU_L0
from aiv_schema.models import NODE_DN3

ARK_DEFAULT_BASE = "https://ark.cn-beijing.volces.com/api/v3"
_FLASH_MARK = "flash"


def _supports_sequential(model: str) -> bool:
    """Seedream flash rejects sequential_image_generation (HTTP 400 InvalidParameter)."""
    name = (model or "").strip().lower()
    return bool(name) and name != SKU_L0.lower() and _FLASH_MARK not in name


class ArkSeedreamClient:
    name = "ark"
    supports_sequential = True
    max_refs = 10

    def __init__(self, settings: Settings) -> None:
        key = getattr(settings, "ark_api_key", None)
        if not key:
            raise AppError(
                422,
                "provider",
                "ARK_API_KEY missing; look Ark client is isolated from AIV_OPENAI_API_KEY/DeepSeek",
                node=NODE_DN3,
                provider=self.name,
            )
        self.api_key = key
        self.base_url = (getattr(settings, "ark_base_url", None) or ARK_DEFAULT_BASE).rstrip("/")
        self.default_sku = getattr(settings, "look_sku", None) or DEFAULT_SKU

    def set_watermark(self, enabled: bool) -> bool:
        return False if not enabled else False

    def generate(
        self,
        prompt: str,
        refs: list[dict[str, Any]],
        frozen_params: FrozenParams,
        seed: int | None = None,
        *,
        sku: str | None = None,
    ) -> ImageResult:
        model = sku or self.default_sku
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "size": frozen_params.size,
            "watermark": False,
            "response_format": frozen_params.response_format,
        }
        if _supports_sequential(model):
            body["sequential_image_generation"] = frozen_params.sequential_image_generation
        if frozen_params.output_format:
            body["output_format"] = frozen_params.output_format
        if seed is not None:
            body["seed"] = int(seed)
        images_in = _local_ref_payloads(refs)[:1]
        if images_in:
            body["image"] = images_in[0]

        url = f"{self.base_url}/images/generations"
        try:
            resp = httpx.post(
                url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=120.0,
            )
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise look_provider_error(502, f"Ark Seedream request failed: {exc}", provider=self.name) from exc

        if resp.status_code >= 400:
            raise look_provider_error(
                resp.status_code,
                f"Ark Seedream HTTP {resp.status_code}: {resp.text[:300]}",
                body=resp.text,
                provider=self.name,
            )
        payload = resp.json()
        images, urls, replay = _parse_ark_images(payload)
        if not images:
            raise look_provider_error(502, "Ark Seedream returned no image bytes", body=payload, provider=self.name)
        returned_seed = _maybe_int((payload.get("data") or [{}])[0].get("seed") if payload.get("data") else payload.get("seed"))
        return ImageResult(
            images=images,
            sku=model,
            provider=self.name,
            seed=returned_seed if returned_seed is not None else seed,
            seed_replay=replay,
            raw_urls=urls,
        )


def _local_ref_payloads(refs: list[dict[str, Any]]) -> list[str]:
    import base64
    from pathlib import Path

    mime_by_suffix = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    out: list[str] = []
    for ref in refs or []:
        path = (ref.get("local_path") or ref.get("abs_path") or "").strip()
        if not path:
            continue
        raw = Path(path)
        if not raw.is_file():
            continue
        mime = mime_by_suffix.get(raw.suffix.lower(), "image/png")
        b64 = base64.b64encode(raw.read_bytes()).decode("ascii")
        out.append(f"data:{mime};base64,{b64}")
    return out


def _maybe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_ark_images(payload: dict[str, Any]) -> tuple[list[bytes], list[str], str]:
    images: list[bytes] = []
    urls: list[str] = []
    replay = "ok"
    rows = payload.get("data") or payload.get("output") or []
    if isinstance(rows, dict):
        rows = rows.get("data") or [rows]
    for row in rows:
        if not isinstance(row, dict):
            continue
        b64 = row.get("b64_json") or row.get("b64")
        if b64:
            images.append(decode_b64_image(str(b64)))
            continue
        url = (row.get("url") or "").strip()
        if url:
            urls.append(url)
            images.append(_download_bytes(url))
    if urls and not any(True for row in rows if isinstance(row, dict) and row.get("b64_json")):
        replay = "partial" if payload.get("seed") is None else "ok"
    if payload.get("seed") is None and not any(
        isinstance(row, dict) and row.get("seed") is not None for row in rows
    ):
        replay = "partial"
    return images, urls, replay


def _download_bytes(url: str) -> bytes:
    try:
        resp = httpx.get(url, timeout=60.0)
        resp.raise_for_status()
        if not resp.content:
            raise ValueError("empty image body")
        return resp.content
    except Exception as exc:  # noqa: BLE001
        raise look_provider_error(502, f"Ark image download failed: {exc}", provider="ark") from exc
