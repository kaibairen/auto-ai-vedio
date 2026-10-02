"""N5b ForcePass=never."""

from __future__ import annotations

from typing import Any

from aiv_drama.errors import AppError
from aiv_drama.validate import FORCE_KEYS
from aiv_drama_n5b.constants import G5_FORCE_MESSAGE
from aiv_schema.models import GATE_G5, NODE_DN5B


def reject_force_keys_n5b(body: dict[str, Any] | None) -> None:
    if not isinstance(body, dict):
        return
    for key in FORCE_KEYS:
        if key in body:
            raise AppError(
                400,
                "force_pass_forbidden",
                G5_FORCE_MESSAGE,
                field=key,
                node=NODE_DN5B,
                gate=GATE_G5,
            )
