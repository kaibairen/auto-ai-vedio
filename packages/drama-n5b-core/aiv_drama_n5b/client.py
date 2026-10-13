"""Ark Seedance 2.0 tasks client. HTTP is injectable. Default = no live POST."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import httpx

from aiv_drama.errors import AppError
from aiv_drama_n5b.constants import (
    ARK_DEFAULT_BASE_URL,
    LIVE_JOB_FORBIDDEN_MESSAGE,
    LIVE_JOB_ENV,
    SEEDANCE_SKU_PRIMARY,
    TASKS_PATH,
)
from aiv_schema.models import NODE_DN5B

_BEARER_RE = re.compile(r"Bearer\s+\S+", re.I)
_DATA_URL_RE = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=\s]+")


def redact_secrets(text: str, api_key: str | None = None) -> str:
    out = str(text)
    if api_key:
        out = out.replace(api_key, "***")
    out = _BEARER_RE.sub("Bearer ***", out)
    out = _DATA_URL_RE.sub("data:image/***;base64,<redacted>", out)
    return out


def tasks_url(base_url: str | None = None, task_id: str | None = None) -> str:
    root = (base_url or ARK_DEFAULT_BASE_URL).rstrip("/")
    if task_id:
        return f"{root}{TASKS_PATH}/{task_id}"
    return f"{root}{TASKS_PATH}"


def parse_task_id(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("id", "task_id"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    data = payload.get("data")
    if isinstance(data, dict):
        return parse_task_id(data)
    return None


def parse_task_status(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    if isinstance(status, str) and status.strip():
        return status.strip()
    data = payload.get("data")
    if isinstance(data, dict):
        return parse_task_status(data)
    return None


def parse_video_url(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    content = payload.get("content")
    if isinstance(content, dict):
        url = content.get("video_url")
        if isinstance(url, str) and url.startswith("http"):
            return url
    url = payload.get("video_url")
    if isinstance(url, str) and url.startswith("http"):
        return url
    data = payload.get("data")
    if isinstance(data, dict):
        return parse_video_url(data)
    return None


def recorded_create_request(body: dict[str, Any], *, base_url: str | None = None) -> dict[str, Any]:
    """Dry-run / CI recorded contract. No key, no POST."""
    return {
        "provider": "ark",
        "endpoint": tasks_url(base_url),
        "method": "POST",
        "path": TASKS_PATH,
        "requested_model": body.get("model") or SEEDANCE_SKU_PRIMARY,
        "body_keys": sorted(body),
        "posted": False,
        "skeleton": True,
    }


def _status_code(resp: Any) -> int | None:
    code = getattr(resp, "status_code", None)
    return int(code) if code is not None else None


class ArkSeedanceClient:
    """Seedance 2.0 tasks API. create_task requires allow_live=True (tests mock HTTP)."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str | None = None,
        allow_live: bool = False,
        timeout: float = 60.0,
        post: Callable[..., Any] | None = None,
        get: Callable[..., Any] | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = (base_url or ARK_DEFAULT_BASE_URL).rstrip("/")
        self.allow_live = bool(allow_live)
        self.timeout = timeout
        self._post = post or httpx.post
        self._get = get or httpx.get

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise AppError(
                422,
                "provider",
                "ARK_API_KEY missing; live Job blocked (never echo)",
                node=NODE_DN5B,
            )
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def create_task(self, body: dict[str, Any]) -> dict[str, Any]:
        if not self.allow_live:
            raise AppError(
                409,
                "live_job_forbidden",
                LIVE_JOB_FORBIDDEN_MESSAGE,
                node=NODE_DN5B,
                posted=False,
                live_job_env=LIVE_JOB_ENV,
            )
        try:
            resp = self._post(
                tasks_url(self.base_url),
                headers=self._headers(),
                json=body,
                timeout=self.timeout,
            )
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                502,
                "provider",
                redact_secrets(f"Ark create task failed: {exc}", self.api_key),
                node=NODE_DN5B,
                posted=False,
            ) from exc
        status = _status_code(resp)
        if status == 401:
            raise AppError(502, "provider", "Ark unauthorized (key rejected). Key is not logged.", node=NODE_DN5B)
        try:
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                502,
                "provider",
                redact_secrets(getattr(resp, "text", "") or str(exc), self.api_key),
                node=NODE_DN5B,
                http=status,
            ) from exc
        task_id = parse_task_id(payload)
        return {
            "ok": status == 200,
            "http": status,
            "id": task_id,
            "task_id": task_id,
            "payload_keys": sorted(payload) if isinstance(payload, dict) else [],
            "posted": True,
        }

    def get_task(self, task_id: str) -> dict[str, Any]:
        if not self.allow_live:
            raise AppError(
                409,
                "live_job_forbidden",
                LIVE_JOB_FORBIDDEN_MESSAGE,
                node=NODE_DN5B,
                posted=False,
            )
        try:
            resp = self._get(
                tasks_url(self.base_url, task_id),
                headers=self._headers(),
                timeout=self.timeout,
            )
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                502,
                "provider",
                redact_secrets(f"Ark get task failed: {exc}", self.api_key),
                node=NODE_DN5B,
            ) from exc
        status = _status_code(resp)
        try:
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                502,
                "provider",
                redact_secrets(getattr(resp, "text", "") or str(exc), self.api_key),
                node=NODE_DN5B,
                http=status,
            ) from exc
        return {
            "ok": status == 200,
            "http": status,
            "id": parse_task_id(payload) or task_id,
            "status": parse_task_status(payload),
            "video_url": parse_video_url(payload),
            "payload_keys": sorted(payload) if isinstance(payload, dict) else [],
        }
