"""Seedance 2 video client. Exactly one attempt per call. No SKU walk. No key logging."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from typing import Any

import httpx

from aiv_drama.errors import AppError
from aiv_drama_n3.seedream import redact_secrets
from aiv_schema.models import NODE_DN4

SEEDANCE_VIDEOS_URL = "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
SEEDANCE_MODEL = "doubao-seedance-1-0-pro"
_BEARER_RE = re.compile(r"Bearer\s+\S+", re.I)


def _status_code(resp: Any) -> int | None:
    code = getattr(resp, "status_code", None)
    return int(code) if code is not None else None


def _parse_video(payload: Any) -> tuple[bytes | None, str | None, str | None]:
    if not isinstance(payload, dict):
        return None, None, None
    req_id = payload.get("id") or payload.get("request_id") or payload.get("provider_request_id")
    if isinstance(req_id, str):
        req_id = req_id.strip() or None
    else:
        req_id = None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if isinstance(data, dict):
        raw = data.get("bytes") or data.get("content")
        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw), None, req_id
        if isinstance(raw, str) and raw:
            return raw.encode("utf-8"), None, req_id
        url = data.get("url") or data.get("video_url")
        if isinstance(url, str) and url.startswith("http"):
            return None, url, req_id
    content = payload.get("content")
    if isinstance(content, (bytes, bytearray)):
        return bytes(content), None, req_id
    return None, None, req_id


def generate_seedance_segment(
    *,
    api_key: str | None,
    prompt: str,
    duration_s: int,
    aspect: str,
    endpoint: str = SEEDANCE_VIDEOS_URL,
    timeout: float = 180.0,
    post: Callable[..., Any] | None = None,
    get: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """One HTTP generate. Failures do not retry another model or segment."""
    if post is None and not api_key:
        raise AppError(
            502,
            "provider",
            "Seedance key missing; this segment's only attempt is consumed. Key is not logged.",
            node=NODE_DN4,
        )
    post_fn = post or httpx.post
    get_fn = get or httpx.get
    body = {
        "model": SEEDANCE_MODEL,
        "prompt": prompt,
        "duration": duration_s,
        "aspect_ratio": aspect,
        "watermark": False,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = post_fn(endpoint, headers=headers, json=body, timeout=timeout)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AppError(
            502,
            "provider",
            redact_secrets(f"Seedance generate failed: {exc}", api_key),
            node=NODE_DN4,
        ) from exc
    status = _status_code(resp)
    if status == 401:
        raise AppError(
            502,
            "provider",
            "Seedance unauthorized (key rejected). Key is not logged.",
            node=NODE_DN4,
            http=status,
        )
    if status not in {200, 201}:
        text = redact_secrets(getattr(resp, "text", "") or f"http {status}", api_key)
        raise AppError(
            502,
            "provider",
            redact_secrets(f"Seedance generate failed: {text}", api_key),
            node=NODE_DN4,
            http=status,
        )
    try:
        payload = resp.json()
    except Exception:
        raw = getattr(resp, "content", None)
        if isinstance(raw, (bytes, bytearray)) and raw:
            digest = hashlib.md5(bytes(raw)).hexdigest()
            req_id = getattr(getattr(resp, "headers", {}), "get", lambda *_: None)("x-request-id")
            return {
                "bytes": bytes(raw),
                "output_md5": digest,
                "provider_request_id": req_id,
                "model": SEEDANCE_MODEL,
                "attempt": 1,
            }
        raise AppError(502, "provider", "Seedance 200 without JSON or bytes", node=NODE_DN4) from None
    content, url, req_id = _parse_video(payload)
    if content is None and url:
        try:
            img = get_fn(url, timeout=timeout)
            if _status_code(img) != 200 or not getattr(img, "content", None):
                raise AppError(502, "provider", "Seedance video download failed", node=NODE_DN4)
            content = img.content
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                502,
                "provider",
                redact_secrets(f"Seedance download failed: {exc}", api_key),
                node=NODE_DN4,
            ) from exc
    if not content:
        raise AppError(502, "provider", "Seedance 200 without video bytes", node=NODE_DN4)
    return {
        "bytes": content,
        "output_md5": hashlib.md5(content).hexdigest(),
        "provider_request_id": req_id,
        "model": SEEDANCE_MODEL,
        "attempt": 1,
    }
