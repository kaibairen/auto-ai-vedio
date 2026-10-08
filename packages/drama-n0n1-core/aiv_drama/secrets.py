"""Reject API keys in request bodies. Never persist or echo secrets."""

from __future__ import annotations

from typing import Any

from aiv_drama.errors import AppError

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


def reject_retry_flag(body: dict[str, Any] | None) -> None:
    if isinstance(body, dict) and "retry" in body:
        raise AppError(
            400,
            "validation",
            "retry is forbidden; look attempts are capped at 2 including failures",
            field="retry",
        )
