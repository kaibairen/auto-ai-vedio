from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        messages: dict[str, str] | None = None,
        **details: Any,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.messages = messages
        self.details = details

    def _resolved_messages(self) -> dict[str, str]:
        if self.messages and self.messages.get("zh"):
            zh = self.messages.get("zh") or self.message
            en = self.messages.get("en") or zh
            return {"zh": zh, "en": en}
        try:
            from aiv_drama.copy_contract import lookup_messages

            found = lookup_messages(self.code)
        except Exception:  # noqa: BLE001
            found = None
        if found:
            return found
        return {"zh": self.message, "en": self.message}

    def to_envelope(self) -> dict[str, Any]:
        pair = self._resolved_messages()
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": pair["zh"],
                "messages": pair,
                "details": self.details,
            },
        }
