"""Ark Seedream image client for gold-A single-sheet generate (BRIEF-AIV-032).

Minimal body only. Forbidden: sequential_image_generation; CU/LS multi-image fake sheets.
Never log API keys or raw face data-URLs.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import httpx

from aiv_drama.errors import AppError
from aiv_schema.models import NODE_DN3

ARK_IMAGES_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
SEEDREAM_SKU_PRIMARY = "doubao-seedream-5-0-flash-260915"
SEEDREAM_SKU_FALLBACK = (
    "doubao-seedream-5-0-pro-260628",
    "doubao-seedream-4-5-251128",
    "wan2.7-image",
)
SEEDREAM_SKU_CHAIN = (SEEDREAM_SKU_PRIMARY, *SEEDREAM_SKU_FALLBACK)
SHEET_SIZE = "2048x1365"
ARK_BODY_KEYS = ("model", "prompt", "size", "watermark", "response_format", "image")
FORBIDDEN_ARK_KEYS = frozenset({"sequential_image_generation", "output_format"})

_BEARER_RE = re.compile(r"Bearer\s+\S+", re.I)
_DATA_URL_RE = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=\s]+")


def redact_secrets(text: str, api_key: str | None = None) -> str:
    out = str(text)
    if api_key:
        out = out.replace(api_key, "***")
    out = _BEARER_RE.sub("Bearer ***", out)
    out = _DATA_URL_RE.sub("data:image/***;base64,<redacted>", out)
    return out


def face_to_data_url(path: str | Path) -> str:
    raw = Path(path).read_bytes()
    mime = "image/jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    elif raw[:6] in (b"GIF87a", b"GIF89a"):
        mime = "image/gif"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        mime = "image/webp"
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_ark_body(
    *,
    model: str,
    prompt: str,
    image_data_url: str,
    size: str = SHEET_SIZE,
) -> dict[str, Any]:
    body = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "watermark": False,
        "response_format": "url",
        "image": image_data_url,
    }
    leaked = FORBIDDEN_ARK_KEYS.intersection(body)
    if leaked:
        raise AppError(
            400,
            "validation",
            "forbidden Ark body key (sequential_image_generation / output_format)",
            node=NODE_DN3,
            fields=sorted(leaked),
        )
    return body


def recorded_ark_request(
    *,
    model: str,
    prompt: str,
    face_md5: str,
    image_bytes_len: int,
    size: str = SHEET_SIZE,
    endpoint: str = ARK_IMAGES_URL,
) -> dict[str, Any]:
    """Dry-run / CI recorded contract. No key, no data-URL payload."""
    return {
        "provider": "ark",
        "endpoint": endpoint,
        "method": "POST",
        "sku_chain": list(SEEDREAM_SKU_CHAIN),
        "requested_model": model,
        "size": size,
        "watermark": False,
        "response_format": "url",
        "body_keys": list(ARK_BODY_KEYS),
        "forbidden_absent": sorted(FORBIDDEN_ARK_KEYS),
        "image": f"data-url redacted · bytes={image_bytes_len} · md5={face_md5}",
        "prompt_chars": len(prompt),
        "sequential_image_generation": False,
        "split_cu_ls": False,
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


def generate_seedream_sheet(
    *,
    api_key: str,
    prompt: str,
    image_data_url: str,
    models: Sequence[str] | None = None,
    size: str = SHEET_SIZE,
    endpoint: str = ARK_IMAGES_URL,
    timeout: float = 120.0,
    post: Callable[..., Any] | None = None,
    get: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """One call hits exactly one SKU. Failures do not walk SEEDREAM_SKU_CHAIN."""
    if not api_key:
        raise AppError(
            422,
            "provider",
            "ARK_API_KEY missing; live generate blocked (use dry_run or set key — never echo)",
            node=NODE_DN3,
        )
    model = (models[0] if models else SEEDREAM_SKU_PRIMARY) or SEEDREAM_SKU_PRIMARY
    post_fn = post or httpx.post
    get_fn = get or httpx.get
    attempts: list[dict[str, Any]] = []
    body = build_ark_body(model=model, prompt=prompt, image_data_url=image_data_url, size=size)
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
        raise AppError(
            502,
            "provider",
            redact_secrets(f"Ark sheet generate failed: {last_detail}", api_key),
            node=NODE_DN3,
            attempts=attempts,
        ) from exc
    status = _status_code(resp)
    if status == 401:
        attempts.append({"model": model, "http": status, "status": "unauthorized", "image": False})
        raise AppError(
            502,
            "provider",
            "Ark unauthorized (key rejected). Key is not logged.",
            node=NODE_DN3,
            attempts=attempts,
        )
    if status != 200:
        last_detail = redact_secrets(getattr(resp, "text", "") or f"http {status}", api_key)
        attempts.append({"model": model, "http": status, "status": "rejected", "image": False})
        raise AppError(
            502,
            "provider",
            redact_secrets(f"Ark sheet generate failed: {last_detail}", api_key),
            node=NODE_DN3,
            attempts=attempts,
        )
    try:
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        last_detail = redact_secrets(str(exc), api_key)
        attempts.append({"model": model, "http": status, "status": "bad_json", "image": False})
        raise AppError(
            502,
            "provider",
            redact_secrets(f"Ark sheet generate failed: {last_detail}", api_key),
            node=NODE_DN3,
            attempts=attempts,
        ) from exc
    url = _parse_image_url(payload)
    if not url:
        last_detail = "Ark 200 without image url"
        attempts.append({"model": model, "http": status, "status": "no_url", "image": False})
        raise AppError(
            502,
            "provider",
            redact_secrets(f"Ark sheet generate failed: {last_detail}", api_key),
            node=NODE_DN3,
            attempts=attempts,
        )
    try:
        img = get_fn(url, timeout=timeout)
        img_status = _status_code(img)
        if img_status != 200:
            last_detail = f"image download http {img_status}"
            attempts.append({"model": model, "http": status, "status": "download_fail", "image": False})
            raise AppError(
                502,
                "provider",
                redact_secrets(f"Ark sheet generate failed: {last_detail}", api_key),
                node=NODE_DN3,
                attempts=attempts,
            )
        content = img.content
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        last_detail = redact_secrets(str(exc), api_key)
        attempts.append({"model": model, "http": status, "status": "download_error", "image": False})
        raise AppError(
            502,
            "provider",
            redact_secrets(f"Ark sheet generate failed: {last_detail}", api_key),
            node=NODE_DN3,
            attempts=attempts,
        ) from exc
    if not content:
        last_detail = "empty image bytes"
        attempts.append({"model": model, "http": status, "status": "empty", "image": False})
        raise AppError(
            502,
            "provider",
            redact_secrets(f"Ark sheet generate failed: {last_detail}", api_key),
            node=NODE_DN3,
            attempts=attempts,
        )
    attempts.append({"model": model, "http": status, "status": "ok", "image": True})
    return {
        "model": model,
        "bytes": content,
        "url_host_only": True,
        "attempts": attempts,
        "size": size,
    }
