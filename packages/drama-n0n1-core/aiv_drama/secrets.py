"""Reject API keys in request bodies. Never persist or echo secrets."""

from __future__ import annotations

import hmac
from typing import Any

from aiv_drama.config import read_user_grant_secret
from aiv_drama.errors import AppError

USER_GRANT_HEADER = "X-AIV-User-Grant"

SECRET_FIELD_KEYS = frozenset(
    {
        "api_key",
        "ark_api_key",
        "openai_api_key",
        "authorization",
        "access_token",
        "secret",
        "bearer",
        "x_api_key",
        "ark_key",
        "x-aiv-user-grant",
        "x_aiv_user_grant",
        "aiv_user_grant_secret",
        "user_grant_secret",
        "grant_secret",
    }
)


def reject_secret_fields(body: dict[str, Any] | None) -> None:
    if not isinstance(body, dict):
        return
    leaked = [
        key
        for key in body
        if str(key).lower() in SECRET_FIELD_KEYS or str(key).lower().endswith("_api_key")
    ]
    if leaked:
        raise AppError(
            400,
            "validation",
            "API keys are not accepted in request bodies",
            fields=sorted(leaked),
        )


def require_user_grant(presented: str | None) -> None:
    """Constant-time check of X-AIV-User-Grant. Missing config or mismatch → 401."""
    configured = read_user_grant_secret()
    if not configured:
        raise AppError(401, "unauthorized", "user grant is not configured")
    incoming = "" if presented is None else str(presented)
    try:
        matched = hmac.compare_digest(incoming.encode("utf-8"), configured.encode("utf-8"))
    except Exception:  # noqa: BLE001
        matched = False
    if not matched:
        raise AppError(401, "unauthorized", "user grant required")


def reject_retry_flag(body: dict[str, Any] | None) -> None:
    if isinstance(body, dict) and "retry" in body:
        raise AppError(
            400,
            "validation",
            "retry is forbidden; look attempts are capped at 2 including failures",
            field="retry",
        )
