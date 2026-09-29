from __future__ import annotations

from typing import Any

from aiv_n1.errors import AppError
from aiv_n1.validate import reject_force


def require_n1_locked(meta: dict[str, Any] | None) -> dict[str, Any]:
    """Downstream hook. Unlocked N1 → 409 upstream_unlocked."""
    if not meta or not meta.get("locked"):
        raise AppError(
            409,
            "upstream_unlocked",
            "downstream read of N1 定稿 requires locked=true (G1 pass)",
            node="N1",
            locked=False,
        )
    return meta


def confirm_payload_forbidden(raw: dict | None) -> None:
    reject_force(raw)
