"""CAM 检 G1–G10 checklist (CHECKLIST-AIV-036-N5-CAM).

门 G4 ≠ 检 G1–G10. ≥7/9 is documented, **not** hard-gated this IMPL.
SCENE EXEMPT → 检 G4 场项 N/A；CHAR 身份项仍硬.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from aiv_drama_n5a.exempt import SCENE_NA_REASON, scene_exempt_label, scene_look_exempt

CHECK_G_ITEMS: tuple[dict[str, Any], ...] = (
    {"id": "G1", "item": "脸一致", "group": "char_identity", "hard": True, "veto": True},
    {"id": "G2", "item": "服装", "group": "char_identity", "hard": True, "veto": False},
    {"id": "G3", "item": "发型", "group": "char_identity", "hard": True, "veto": False},
    {"id": "G4", "item": "场景", "group": "scene", "hard": True, "veto": False},
    {"id": "G5", "item": "景别", "group": "visual", "hard": False, "veto": False},
    {"id": "G6", "item": "运镜可读", "group": "visual", "hard": False, "veto": False},
    {"id": "G7", "item": "手/肢体", "group": "anatomy", "hard": True, "veto": True},
    {"id": "G8", "item": "文字乱码", "group": "text", "hard": True, "veto": True},
    {"id": "G9", "item": "多角色", "group": "char_identity", "hard": True, "veto": False},
    {"id": "G10", "item": "崩坏", "group": "collapse", "hard": True, "veto": False},
)

PRECHECK_ITEMS: tuple[dict[str, Any], ...] = (
    {"id": "P-A1", "item": "宫格文件存在且 md5 与 evidence 一致"},
    {"id": "P-A2", "item": "字节来自真实图 API（禁彩条/占位/手绘拼贴）"},
    {"id": "P-A3", "item": "单张拼格；格数与文件名/声明一致"},
)

THRESHOLD_NOTE = (
    "CAM 建议 9 格 ≥7/9 无硬伤；比率升硬门前须挂起面/CTO。"
    "本 IMPL **未硬钉** ≥7/9；狗粮以无硬伤 + 记录抽检出门。"
)
VERDICT_UNPINNED = "PASS(建议阈未钉)"
ALLOWED_ITEM_VERDICTS = frozenset({"PASS", "FAIL", "N/A", "pending", SCENE_NA_REASON})


def _item_row(spec: dict[str, Any], *, verdict: str, reason: str | None = None) -> dict[str, Any]:
    row = {
        "id": spec["id"],
        "item": spec["item"],
        "group": spec["group"],
        "hard": spec["hard"],
        "veto": spec["veto"],
        "verdict": verdict,
    }
    if reason:
        row["reason"] = reason
    return row


def build_checklist(
    *,
    rec: dict[str, Any],
    ep: str,
    layout: int,
    grid_relpath: str | None,
    md5: str | None,
    sku: str | None,
    look_modes: dict[str, str] | None = None,
    precheck: dict[str, str] | None = None,
    fake_pixels: bool = False,
) -> dict[str, Any]:
    exempt = scene_look_exempt(rec, ep)
    items: dict[str, Any] = {}
    for spec in CHECK_G_ITEMS:
        if spec["id"] == "G4" and exempt:
            items[spec["id"]] = _item_row(spec, verdict=SCENE_NA_REASON, reason=scene_exempt_label(rec, ep))
            items[spec["id"]]["hard"] = False
        else:
            items[spec["id"]] = _item_row(spec, verdict="pending")
    pa = {row["id"]: "pending" for row in PRECHECK_ITEMS}
    if precheck:
        pa.update(precheck)
    return {
        "schema": "aiv-036-n5a-g4-checklist-v0",
        "episode": ep,
        "grid_path": grid_relpath,
        "md5": md5,
        "sku": sku,
        "layout": layout,
        "scene_exempt": exempt,
        "scene_exempt_label": scene_exempt_label(rec, ep),
        "look_modes": dict(look_modes or {}),
        "p_char": "usable_for_n4=true = human-reviewed look sheet (合板), not necessarily a face file",
        "mode_b": "thick-card text look is enough; missing face file is not an N5a hard block",
        "precheck": pa,
        "items": items,
        "threshold_note": THRESHOLD_NOTE,
        "threshold_hard_gated": False,
        "suggested_pass_rate": {"9": ">=7/9", "16": ">=13/16"},
        "veto": {
            "fake_pixels": bool(fake_pixels),
            "identity_drift": None,
            "malformed_hands": None,
            "garbled_text": None,
        },
        "verdict_g4": "pending",
        "fake_pixels": "yes" if fake_pixels else "none",
        "docs_pass": False,
    }


def apply_gate_to_checklist(
    checklist: dict[str, Any],
    *,
    verdict: str,
    actor: str,
    note: str | None = None,
    decided_at: str | None = None,
) -> dict[str, Any]:
    out = deepcopy(checklist)
    if verdict == "pass":
        out["verdict_g4"] = VERDICT_UNPINNED
    elif verdict == "rework":
        out["verdict_g4"] = "FAIL"
    else:
        out["verdict_g4"] = verdict
    out["gate_actor"] = actor
    out["gate_note"] = note
    out["gate_decided_at"] = decided_at
    return out


def veto_blocks_pass(checklist: dict[str, Any] | None) -> list[str]:
    reasons: list[str] = []
    if not checklist:
        return ["missing_checklist"]
    if checklist.get("fake_pixels") in {"yes", True} or (checklist.get("veto") or {}).get("fake_pixels"):
        reasons.append("fake_pixels")
    pre = checklist.get("precheck") or {}
    if str(pre.get("P-A2") or "").upper() == "FAIL":
        reasons.append("P-A2")
    if str(pre.get("P-A1") or "").upper() == "FAIL":
        reasons.append("P-A1")
    items = checklist.get("items") or {}
    for spec in CHECK_G_ITEMS:
        row = items.get(spec["id"]) or {}
        verdict = str(row.get("verdict") or "")
        if verdict.upper() != "FAIL":
            continue
        if spec["id"] == "G4" and verdict in {SCENE_NA_REASON, "N/A"}:
            continue
        if spec.get("veto") or spec.get("hard"):
            reasons.append(spec["id"])
    return reasons
