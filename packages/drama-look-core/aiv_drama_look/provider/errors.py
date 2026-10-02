from __future__ import annotations

from typing import Any

from aiv_drama.errors import AppError
from aiv_schema.models import NODE_DN3

CLASS_AUTH = "auth"
CLASS_QUOTA = "quota"
CLASS_5XX = "5xx"
CLASS_FILTER = "content_filter"
CLASS_API = "api_fail"


def classify_http_error(status: int, body: Any) -> str:
    if status in {401, 403}:
        return CLASS_AUTH
    if status == 429:
        return CLASS_QUOTA
    if status >= 500:
        return CLASS_5XX
    text = str(body or "").lower()
    markers = ("content_filter", "sensitive", "审核", "risk", "moderation", "output_image_sensitive")
    if any(m in text for m in markers):
        return CLASS_FILTER
    return CLASS_API


def look_provider_error(status: int, message: str, *, body: Any = None, provider: str) -> AppError:
    classified = classify_http_error(status, body if body is not None else message)
    http = 422 if classified == CLASS_AUTH else 502
    return AppError(
        http,
        "provider",
        message,
        node=NODE_DN3,
        provider=provider,
        classified=classified,
        upgrade_reason="api_fail",
    )


def decode_b64_image(raw: str) -> bytes:
    import base64

    text = (raw or "").strip()
    if "," in text and text.lower().startswith("data:"):
        text = text.split(",", 1)[1]
    return base64.b64decode(text)
