"""DashScope wan · multimodal-generation · DASHSCOPE_API_KEY only (Beijing host default)."""

from __future__ import annotations

from typing import Any

import httpx

from aiv_drama.config import Settings
from aiv_drama.errors import AppError
from aiv_drama_look.provider.base import FrozenParams, ImageResult
from aiv_drama_look.provider.errors import decode_b64_image, look_provider_error
from aiv_drama_look.sku import SKU_F0
from aiv_schema.models import NODE_DN3

DASHSCOPE_DEFAULT_BASE = "https://dashscope.aliyuncs.com/api/v1"


class DashScopeWanClient:
    name = "dashscope"
    supports_sequential = True
    max_refs = 9

    def __init__(self, settings: Settings) -> None:
        key = getattr(settings, "dashscope_api_key", None)
        if not key:
            raise AppError(
                422,
                "provider",
                "DASHSCOPE_API_KEY missing; look wan client is isolated from AIV_OPENAI_API_KEY/DeepSeek",
                node=NODE_DN3,
                provider=self.name,
            )
        self.api_key = key
        self.base_url = (getattr(settings, "dashscope_base_url", None) or DASHSCOPE_DEFAULT_BASE).rstrip("/")

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
        model = sku or SKU_F0
        content: list[dict[str, Any]] = []
        for item in _local_ref_payloads(refs)[:1]:
            content.append({"image": item})
        content.append({"text": prompt})
        body: dict[str, Any] = {
            "model": model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": {
                "n": frozen_params.n,
                "size": frozen_params.size.replace("x", "*"),
                "watermark": False,
                "enable_sequential": bool(frozen_params.enable_sequential),
            },
        }
        if seed is not None:
            body["parameters"]["seed"] = int(seed)

        url = f"{self.base_url}/services/aigc/multimodal-generation/generation"
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
            raise look_provider_error(502, f"DashScope wan request failed: {exc}", provider=self.name) from exc

        if resp.status_code >= 400:
            raise look_provider_error(
                resp.status_code,
                f"DashScope wan HTTP {resp.status_code}: {resp.text[:300]}",
                body=resp.text,
                provider=self.name,
            )
        payload = resp.json()
        images, urls, replay = _parse_wan_images(payload)
        if not images:
            raise look_provider_error(502, "DashScope wan returned no image bytes", body=payload, provider=self.name)
        returned_seed = _maybe_int((payload.get("output") or {}).get("seed") or payload.get("seed"))
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

    out: list[str] = []
    for ref in refs or []:
        path = (ref.get("local_path") or ref.get("abs_path") or "").strip()
        if not path:
            continue
        raw = Path(path)
        if not raw.is_file():
            continue
        b64 = base64.b64encode(raw.read_bytes()).decode("ascii")
        out.append(f"data:image/png;base64,{b64}")
    return out


def _maybe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_wan_images(payload: dict[str, Any]) -> tuple[list[bytes], list[str], str]:
    images: list[bytes] = []
    urls: list[str] = []
    replay = "ok"
    output = payload.get("output") or {}
    choices = output.get("choices") or output.get("results") or []
    blobs: list[Any] = []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message") or {}
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list):
            blobs.extend(content)
        if choice.get("url"):
            blobs.append(choice)
        if choice.get("image"):
            blobs.append(choice)
    if output.get("results"):
        blobs.extend(output.get("results") or [])
    for item in blobs:
        if not isinstance(item, dict):
            continue
        raw = item.get("image") or item.get("url") or item.get("b64_json")
        if not raw:
            continue
        text = str(raw).strip()
        if text.startswith("data:") or (len(text) > 80 and "://" not in text[:12]):
            images.append(decode_b64_image(text))
            continue
        if text.startswith("http://") or text.startswith("https://"):
            urls.append(text)
            images.append(_download_bytes(text))
    if payload.get("seed") is None and output.get("seed") is None:
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
        raise look_provider_error(502, f"DashScope image download failed: {exc}", provider="dashscope") from exc
