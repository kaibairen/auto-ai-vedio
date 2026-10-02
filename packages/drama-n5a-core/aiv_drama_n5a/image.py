"""Ark/Seedream image client for N5a single-sheet grids.

Reuses N3 Seedream SKU chain / redaction. Supports Mode A img2img (optional
face) and Mode B t2i (no image key). Never writes colorbars or placeholders.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from aiv_drama.errors import AppError
from aiv_drama_n3.seedream import (
    ARK_IMAGES_URL,
    FORBIDDEN_ARK_KEYS,
    SEEDREAM_SKU_CHAIN,
    SEEDREAM_SKU_PRIMARY,
    face_to_data_url,
    redact_secrets,
)
from aiv_schema.models import NODE_DN5A

GRID_SIZE = "2048x2048"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8"
FAKE_MARKERS = (b"COLORBARS", b"PLACEHOLDER_GRID", b"FAKE_PIXELS", b"colorbar")


def assert_real_image_bytes(data: bytes) -> None:
    if not data:
        raise AppError(422, "fake_pixels_forbidden", "empty image bytes", node=NODE_DN5A)
    upper = data[:64].upper()
    if any(marker in data or marker in upper for marker in FAKE_MARKERS):
        raise AppError(
            422,
            "fake_pixels_forbidden",
            "假像素标记（彩条/占位）禁止写入宫格",
            node=NODE_DN5A,
        )
    if not (data.startswith(PNG_MAGIC) or data.startswith(JPEG_MAGIC) or data.startswith(b"RIFF")):
        raise AppError(
            422,
            "fake_pixels_forbidden",
            "字节不是真实图像容器（PNG/JPEG/WEBP）",
            node=NODE_DN5A,
        )


def build_grid_ark_body(
    *,
    model: str,
    prompt: str,
    image_data_url: str | None = None,
    size: str = GRID_SIZE,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "watermark": False,
        "response_format": "url",
    }
    if image_data_url:
        body["image"] = image_data_url
    leaked = FORBIDDEN_ARK_KEYS.intersection(body)
    if leaked:
        raise AppError(
            400,
            "validation",
            "forbidden Ark body key (sequential_image_generation / output_format)",
            node=NODE_DN5A,
            fields=sorted(leaked),
        )
    return body


def recorded_grid_request(
    *,
    model: str,
    prompt: str,
    look_mode: str,
    has_image: bool,
    face_md5: str | None = None,
    size: str = GRID_SIZE,
    endpoint: str = ARK_IMAGES_URL,
) -> dict[str, Any]:
    return {
        "provider": "ark",
        "endpoint": endpoint,
        "method": "POST",
        "sku_chain": list(SEEDREAM_SKU_CHAIN),
        "requested_model": model,
        "size": size,
        "watermark": False,
        "response_format": "url",
        "look_mode": look_mode,
        "image": ("data-url redacted · md5=" + face_md5) if has_image else None,
        "prompt_chars": len(prompt),
        "sequential_image_generation": False,
        "fake_pixels": False,
        "key_redacted": True,
    }


def _status_code(resp: Any) -> int | None:
    code = getattr(resp, "status_code", None)
    return int(code) if code is not None else None


def _parse_image_url(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            url = first.get("url")
            if isinstance(url, str) and url.startswith("http"):
                return url
    url = payload.get("url")
    if isinstance(url, str) and url.startswith("http"):
        return url
    return None


def generate_grid_image(
    *,
    api_key: str,
    prompt: str,
    image_data_url: str | None = None,
    models: tuple[str, ...] = SEEDREAM_SKU_CHAIN,
    size: str = GRID_SIZE,
    endpoint: str = ARK_IMAGES_URL,
    timeout: float = 120.0,
    post: Callable[..., Any] | None = None,
    get: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    if not api_key:
        raise AppError(
            422,
            "provider",
            "ARK_API_KEY missing; N5a live generate BLOCKED (dry_run for contract only — never fake-pixel PASS)",
            node=NODE_DN5A,
            blocked=True,
            written=False,
            fake_pixels=False,
            dry_run_hint=True,
        )
    post_fn = post or httpx.post
    get_fn = get or httpx.get
    attempts: list[dict[str, Any]] = []
    last_detail = "no attempt"
    for model in models:
        body = build_grid_ark_body(model=model, prompt=prompt, image_data_url=image_data_url, size=size)
        try:
            resp = post_fn(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=timeout,
            )
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_detail = redact_secrets(str(exc), api_key)
            attempts.append({"model": model, "http": None, "status": "error", "image": False})
            continue
        status = _status_code(resp)
        if status == 401:
            attempts.append({"model": model, "http": status, "status": "unauthorized", "image": False})
            raise AppError(
                502,
                "provider",
                "Ark unauthorized (key rejected). Key is not logged.",
                node=NODE_DN5A,
                attempts=attempts,
            )
        if status != 200:
            last_detail = redact_secrets(getattr(resp, "text", "") or f"http {status}", api_key)
            attempts.append({"model": model, "http": status, "status": "rejected", "image": False})
            continue
        try:
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            last_detail = redact_secrets(str(exc), api_key)
            attempts.append({"model": model, "http": status, "status": "bad_json", "image": False})
            continue
        url = _parse_image_url(payload)
        if not url:
            last_detail = "Ark 200 without image url"
            attempts.append({"model": model, "http": status, "status": "no_url", "image": False})
            continue
        try:
            img = get_fn(url, timeout=timeout)
            img_status = _status_code(img)
            if img_status != 200:
                last_detail = f"image download http {img_status}"
                attempts.append({"model": model, "http": status, "status": "download_fail", "image": False})
                continue
            content = img.content
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_detail = redact_secrets(str(exc), api_key)
            attempts.append({"model": model, "http": status, "status": "download_error", "image": False})
            continue
        try:
            assert_real_image_bytes(content)
        except AppError:
            last_detail = "API bytes failed real-image check"
            attempts.append({"model": model, "http": status, "status": "fake_pixels", "image": False})
            continue
        attempts.append({"model": model, "http": status, "status": "ok", "image": True})
        return {
            "model": model,
            "bytes": content,
            "url_host_only": True,
            "attempts": attempts,
            "size": size,
            "has_image_ref": bool(image_data_url),
        }
    raise AppError(
        502,
        "provider",
        redact_secrets(f"Ark grid generate failed: {last_detail}", api_key),
        node=NODE_DN5A,
        attempts=attempts,
        written=False,
        fake_pixels=False,
    )
