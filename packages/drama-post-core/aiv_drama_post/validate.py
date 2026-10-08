from __future__ import annotations

from typing import Any

from aiv_drama.errors import AppError
from aiv_drama.validate import FORCE_KEYS, reject_force_keys

OPEN_ITEM_STATES = frozenset({"blocks_l2", "waiting_on_user", "non_blocking", "closed"})
REVIEW_LEVELS = frozenset({"L1", "L2", "L3"})
COST_OPS = frozenset({"seedream", "seedance", "tts", "llm"})


def reject_force_keys_post(body: dict[str, Any] | None) -> None:
    reject_force_keys(body)
    if not isinstance(body, dict):
        return
    for key in FORCE_KEYS:
        if key in body:
            raise AppError(400, "force_pass_forbidden", "ForcePass=never", field=key)


def is_user_conclusion(conclusion: str) -> bool:
    return (conclusion or "").strip().lower().startswith("user:")
