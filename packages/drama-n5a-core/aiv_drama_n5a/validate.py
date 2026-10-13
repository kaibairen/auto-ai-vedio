"""N5a hard/soft validation. ForcePass=never. Missing jsonl → 409. No fake pixels."""

from __future__ import annotations

from typing import Any

from aiv_drama.errors import AppError
from aiv_drama.validate import FORCE_KEYS
from aiv_schema.models import GATE_G4, NODE_DN5A

G4_FORCE_MESSAGE = "ForcePass=never，禁止跳过门 G4 / N5a"
MISSING_JSONL_MESSAGE = "本集缺少非空 EP##-prompts.jsonl，禁止生成宫格"
EMPTY_JSONL_MESSAGE = "EP##-prompts.jsonl 为空，禁止生成宫格"
LAYOUT_MESSAGE = "狗粮宫格仅 9（默认）或 16；25 后置"
FAKE_PIXELS_MESSAGE = "禁假像素：不得用彩条/占位 PNG 冒充宫格"
MISSING_GRID_MESSAGE = "尚无真图宫格，禁止点门 G4 pass"
G4_VETO_MESSAGE = "检项一票否决（假像素 / 换脸 / 严重畸形 / 大面积乱码）未清，G4 不得 pass"
N5B_LOCKED_MESSAGE = "门 G4 未锁定，禁止 N5b submit"
N5B_NOT_IMPL_MESSAGE = "N5b 出片 Job 本 PR 不做；须先锁门 G4"


def reject_force_keys_n5a(body: dict[str, Any] | None) -> None:
    if not isinstance(body, dict):
        return
    for key in FORCE_KEYS:
        if key in body:
            raise AppError(
                400,
                "force_pass_forbidden",
                G4_FORCE_MESSAGE,
                field=key,
                node=NODE_DN5A,
                gate=GATE_G4,
            )


def normalize_layout(raw: Any) -> int:
    if raw in (None, "", 9, "9"):
        return 9
    if raw in (16, "16"):
        return 16
    if raw in (25, "25"):
        raise AppError(422, "validation", LAYOUT_MESSAGE, layout=raw, node=NODE_DN5A)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise AppError(422, "validation", LAYOUT_MESSAGE, layout=raw, node=NODE_DN5A) from None
    if value == 9:
        return 9
    if value == 16:
        return 16
    raise AppError(422, "validation", LAYOUT_MESSAGE, layout=value, node=NODE_DN5A)
