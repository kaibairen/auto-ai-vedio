from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Structured API/CLI error. Never used to invent ForcePass."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        **extra: Any,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.extra = extra

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error": self.code,
            "message": self.message,
        }
        payload.update(self.extra)
        return payload
