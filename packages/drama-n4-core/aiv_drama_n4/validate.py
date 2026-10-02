"""N4 hard/soft validation. ForcePass=never. Missing refs do not write jsonl."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from aiv_drama.errors import AppError
from aiv_drama.validate import FORCE_KEYS
from aiv_drama_n2.validate import CLASS_D_CAMERAS, CLASS_D_DURATION_FLOOR
from aiv_drama_n3.cards import all_cards, has_usable_ref, is_char_id, is_none_id, is_scene_id
from aiv_drama_n3.char_look import (
    LOOK_USABLE_FALSE_REASON,
    has_reviewed_look_sheet,
    has_usable_char,
    resolve_char_look_policy,
)
from aiv_drama_n3.library import resolve_ref_file
from aiv_drama_n3.scene_look import (
    SCENE_OPTIONAL_WARN,
    is_char_card,
    is_scene_card,
    resolve_scene_look_policy,
)
from aiv_drama_n3.validate import usable_for_n4
from aiv_drama_n4.camera import known_camera, static_fast_conflict
from aiv_drama_n4.tools import lookup_adapter
from aiv_schema.models import GATE_G3, NODE_DN4

G3_FORCE_MESSAGE = "ForcePass=never，禁止跳过 D-N4 硬门"
UPSTREAM_G2_MESSAGE = "D-N2 G2 未锁定，禁止拼装 D-N4"
UPSTREAM_G3_MESSAGE = "D-N3 G3 未锁定，禁止拼装 D-N4"
STALE_UPSTREAM_MESSAGE = "上游 cast/分镜/cards 已升版；请重新拼装 D-N4"
USABLE_FALSE_MESSAGE = "usable_for_n4=false · 缺图/缺 ref，拒绝写盘"
CHAR_USABLE_FALSE_MESSAGE = "usable_for_n4=false · 人物缺合格脸图或 usable=false，拒绝写盘"
NOT_READY_MESSAGE = "ready_for_n4=false · 未选 tool_profile 或分镜硬检未过，拒绝写盘"
BARE_ID_MESSAGE = "prompt 禁止只留裸 CHAR-/SCENE- ID，须替换为中文特征"
EMPTY_NEGATIVE_MESSAGE = "negative 不可为空（NEG_CORE）"
STORYBOARD_EMPTY_MESSAGE = "分镜无行，无法拼装"
MISSING_CARD_MESSAGE = "镜绑定 CHAR/SCENE 无卡，拒绝写盘"

# From KEEP `.prompt/generation/负面提示词.md` after `--no`.
NEG_CORE = (
    "面部变形、五官扭曲、脸部拉伸、面部模糊、五官错位、多眼、少眼、歪嘴、歪鼻、下巴变形、额头变形、"
    "多手、少手、手臂重叠、肢体断裂、身体变形、比例失调、空间扭曲、透视错误、穿模、塑料感、锯齿、"
    "低清、模糊、噪点、AI artifacts、畸形、怪异、恐怖谷、非人类特征"
)
NEG_CORE_MARKERS = ("面部变形", "多手", "比例失调", "低清")

BARE_ID_RE = re.compile(r"(?:CHAR|SCENE)-\d+")

STATUS_BY_CODE = {
    "usable_for_n4_false": 409,
    "missing_ref": 409,
    "missing_file": 409,
    "not_ready_for_n4": 409,
    "upstream_unlocked": 409,
    "g2_unlocked": 409,
    "g3_unlocked": 409,
    "stale_upstream": 409,
    "force_pass_forbidden": 400,
}

FIRST_SHOT_CHECKS = (
    {"id": "Q1", "item": "正词能否认出谁（中文名+特征，非裸 ID）"},
    {"id": "Q2", "item": "场是否像空间（场名+锚）"},
    {"id": "Q3", "item": "action 是否本镜事"},
    {"id": "Q4", "item": "是否一主运镜"},
    {"id": "Q5", "item": "负词非空且含脸/肢/清晰度类"},
    {"id": "Q6", "item": "ref 声明与 ref_images 非空"},
    {"id": "Q7", "item": "无脏名/LK 碎片进主体"},
)


def reject_force_keys_n4(body: dict[str, Any] | None) -> None:
    if not isinstance(body, dict):
        return
    for key in FORCE_KEYS:
        if key in body:
            raise AppError(
                400,
                "force_pass_forbidden",
                G3_FORCE_MESSAGE,
                field=key,
                node=NODE_DN4,
                gate=GATE_G3,
            )


def issue(
    severity: str,
    code: str,
    message: str,
    *,
    shot_id: str | None = None,
    card_id: str | None = None,
    field: str | None = None,
    **details: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "message": message,
        "shot_id": shot_id,
        "card_id": card_id,
        "field": field,
    }
    if details:
        item["details"] = details
    return item


def missing_ref_entry(
    card: dict[str, Any],
    *,
    reason: str,
    path: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": card.get("id"),
        "kind": card.get("kind"),
        "name": card.get("name"),
        "reason": reason,
    }
    if path:
        entry["path"] = path
    return entry


def _card_missing_entries(card: dict[str, Any], settings: Any | None = None) -> list[dict[str, Any]]:
    """Honest missing-image / missing-ref rows for one card. Fake path+md5 without a file is BLOCK."""
    missing: list[dict[str, Any]] = []
    refs = [r for r in (card.get("refs") or []) if isinstance(r, dict)]
    usable_on_disk = False
    saw_missing_file = False
    for ref in refs:
        path = (ref.get("path") or "").strip()
        md5 = (ref.get("md5") or "").strip()
        role = (ref.get("role") or "").strip()
        if card.get("kind") == "character" and role not in {"face", "full"}:
            continue
        found: Path | None = None
        if settings is not None and path:
            found = resolve_ref_file(settings, path)
        elif path:
            raw = Path(path)
            found = raw if raw.is_file() else None
        if found and md5:
            usable_on_disk = True
        elif path and not found:
            saw_missing_file = True
            missing.append(missing_ref_entry(card, reason="missing_file", path=path))
    if not usable_on_disk:
        if not has_usable_ref(card) and not saw_missing_file:
            missing.append(missing_ref_entry(card, reason="missing_ref"))
        elif saw_missing_file:
            return missing
        elif not has_usable_ref(card):
            missing.append(missing_ref_entry(card, reason="missing_ref"))
    return missing


def _dedupe_missing(missing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, Any, Any]] = set()
    out: list[dict[str, Any]] = []
    for item in missing:
        key = (item.get("id"), item.get("reason"), item.get("path"))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def collect_missing_refs(
    n3: dict[str, Any] | None,
    settings: Any | None = None,
    *,
    rec: dict[str, Any] | None = None,
    scene_look: str | None = None,
    include_optional_scenes: bool = False,
) -> list[dict[str, Any]]:
    """Hard missing-image / missing-ref list.

    On SCENE-optional / EXEMPT episodes, SCENE plates are honesty-only unless
    ``include_optional_scenes`` is true. Mode A CHAR face/full missing stays hard.
    Mode B reviewed 合板: missing face file is not a hard missing_ref.
    """
    policy = resolve_scene_look_policy(rec, scene_look=scene_look, n3=n3)
    missing: list[dict[str, Any]] = []
    for card in all_cards(n3):
        if is_scene_card(card) and policy.scene_optional and not include_optional_scenes:
            continue
        if is_char_card(card) and has_reviewed_look_sheet(card, n3):
            continue
        if is_char_card(card) and resolve_char_look_policy(rec, card, n3=n3).mode_b:
            if not has_usable_char(card, n3):
                missing.append(missing_ref_entry(card, reason=LOOK_USABLE_FALSE_REASON))
            continue
        missing.extend(_card_missing_entries(card, settings))
    return _dedupe_missing(missing)


def collect_scene_missing_refs(
    n3: dict[str, Any] | None,
    settings: Any | None = None,
) -> list[dict[str, Any]]:
    """Honesty list of SCENE plates. Never used alone to 409 assemble."""
    missing: list[dict[str, Any]] = []
    for card in all_cards(n3):
        if not is_scene_card(card):
            continue
        missing.extend(_card_missing_entries(card, settings))
    return _dedupe_missing(missing)


def first_shot_review(lines: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not lines:
        return None
    first = lines[0]
    return {
        "shot_id": first.get("shot_id"),
        "severity": "warn",
        "message": "请人工抽查首镜",
        "checks": [dict(item) for item in FIRST_SHOT_CHECKS],
    }


def _index_cards(n3: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in all_cards(n3) if c.get("id")}


def collect_n4_issues(
    rec: dict[str, Any],
    lines: list[dict[str, Any]] | None = None,
    *,
    settings: Any | None = None,
    for_write: bool = False,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    g2 = rec.get("gate_g2") or {}
    g3 = rec.get("gate_g3") or {}
    g3_locked = bool(g3.get("locked"))
    n3 = rec.get("n3")
    cards = (n3 or {}).get("cards") or {}
    sb = rec.get("storyboard") or {}
    policy = resolve_scene_look_policy(rec, n3=n3)
    missing = collect_missing_refs(n3, settings, rec=rec)
    scene_missing = collect_scene_missing_refs(n3, settings) if policy.scene_optional else []
    usable = usable_for_n4(n3, g3_locked=g3_locked, rec=rec) and not missing
    index = _index_cards(n3)
    n2_ids = {row.get("shot_id") for row in (sb.get("rows") or []) if row.get("shot_id")}
    row_by_id = {row.get("shot_id"): row for row in (sb.get("rows") or [])}
    adapter = lookup_adapter("seedance_2")

    if not (g2.get("locked") and sb.get("locked")):
        issues.append(issue("error", "upstream_unlocked", UPSTREAM_G2_MESSAGE, field="gate_g2"))
    if not g3_locked:
        issues.append(issue("error", "upstream_unlocked", UPSTREAM_G3_MESSAGE, field="gate_g3"))
    if not (sb.get("tool_profile") or "").strip() or not sb.get("ready_for_n4"):
        issues.append(issue("error" if for_write else "warn", "not_ready_for_n4", NOT_READY_MESSAGE, field="ready_for_n4"))
    if cards.get("stale"):
        issues.append(issue("warn", "stale_upstream", STALE_UPSTREAM_MESSAGE, field="cards"))
    if not sb.get("rows"):
        issues.append(issue("error", "storyboard_empty", STORYBOARD_EMPTY_MESSAGE, field="rows"))
    if not usable:
        issues.append(
            issue(
                "error",
                "usable_for_n4_false",
                CHAR_USABLE_FALSE_MESSAGE if policy.scene_optional else USABLE_FALSE_MESSAGE,
                field="refs",
                missing_refs=missing,
                scene_look=policy.mode,
            )
        )
        for item in missing:
            issues.append(
                issue(
                    "error",
                    item.get("reason") or "missing_ref",
                    "缺图或缺 ref，不能写 jsonl",
                    card_id=item.get("id"),
                    field="refs",
                    path=item.get("path"),
                    reason=item.get("reason"),
                )
            )
    elif scene_missing:
        for item in scene_missing:
            issues.append(
                issue(
                    "warn",
                    item.get("reason") or "missing_ref",
                    SCENE_OPTIONAL_WARN,
                    card_id=item.get("id"),
                    field="refs",
                    path=item.get("path"),
                    reason=item.get("reason"),
                    scene_look=policy.mode,
                )
            )

    for row in lines or []:
        shot_id = row.get("shot_id")
        prompt = row.get("prompt") or ""
        negative = (row.get("negative") or "").strip()
        src = row_by_id.get(shot_id) or {}
        if n2_ids and shot_id not in n2_ids:
            issues.append(
                issue("error", "validation_failed", "shot_id 不在 N2 分镜行", shot_id=shot_id, field="shot_id")
            )
        if not negative:
            issues.append(issue("error", "empty_negative", EMPTY_NEGATIVE_MESSAGE, shot_id=shot_id, field="negative"))
        elif NEG_CORE not in negative:
            issues.append(
                issue(
                    "warn",
                    "neg_core_missing",
                    "negative 未包含 NEG_CORE 全文",
                    shot_id=shot_id,
                    field="negative",
                )
            )
        if not all(marker in negative for marker in NEG_CORE_MARKERS):
            issues.append(
                issue(
                    "warn" if negative else "error",
                    "neg_core_thin",
                    "negative 未覆盖面部变形/多手/比例失调/低清",
                    shot_id=shot_id,
                    field="negative",
                )
            )
        if BARE_ID_RE.search(prompt):
            issues.append(
                issue(
                    "error",
                    "bare_id_in_prompt",
                    BARE_ID_MESSAGE,
                    shot_id=shot_id,
                    field="prompt",
                    ids=BARE_ID_RE.findall(prompt),
                )
            )
        if not (prompt or "").strip():
            issues.append(issue("error", "empty_prompt", "prompt 不能为空", shot_id=shot_id, field="prompt"))
        if row.get("tool_profile") != "seedance_2":
            issues.append(
                issue(
                    "error" if for_write else "warn",
                    "unsupported_tool_profile",
                    "本拍落盘 tool_profile 必须是 seedance_2",
                    shot_id=shot_id,
                    field="tool_profile",
                    tool_profile=row.get("tool_profile"),
                )
            )
        duration = int(row.get("duration_s") or 0)
        if adapter and duration not in adapter.allowed_durations:
            issues.append(
                issue(
                    "error",
                    "duration_out_of_profile",
                    "duration_s 须落入 seedance_2 档 {5,8,10}",
                    shot_id=shot_id,
                    field="duration_s",
                    duration_s=duration,
                )
            )
        camera = row.get("camera") or src.get("camera")
        if camera and not known_camera(camera):
            issues.append(
                issue("error", "validation_failed", "camera 不在 N2 闭集", shot_id=shot_id, field="camera")
            )
        if camera in CLASS_D_CAMERAS and duration < CLASS_D_DURATION_FLOOR:
            issues.append(
                issue(
                    "error",
                    "duration_below_camera_floor",
                    "Class-D 运镜时长须 ≥8 秒",
                    shot_id=shot_id,
                    field="duration_s",
                    duration_s=duration,
                    camera=camera,
                )
            )
        aspect = row.get("aspect")
        if adapter and aspect and aspect not in adapter.allowed_aspects:
            issues.append(
                issue(
                    "error",
                    "validation_failed",
                    "aspect 须为 9:16 / 16:9 / 2.35:1",
                    shot_id=shot_id,
                    field="aspect",
                    aspect=aspect,
                )
            )
        refs = row.get("ref_images") or []
        if adapter and len(refs) > adapter.max_ref_images:
            issues.append(
                issue(
                    "error",
                    "validation_failed",
                    f"ref_images 不得超过 {adapter.max_ref_images} 张",
                    shot_id=shot_id,
                    field="ref_images",
                )
            )
        if adapter and len(prompt) > adapter.max_prompt_len:
            issues.append(
                issue(
                    "error",
                    "prompt_too_long",
                    f"prompt 超过 adapter 上限 {adapter.max_prompt_len}",
                    shot_id=shot_id,
                    field="prompt",
                    length=len(prompt),
                )
            )
        for cid in row.get("char_ids") or []:
            if is_none_id(cid) or not is_char_id(cid):
                continue
            if cid not in index:
                issues.append(
                    issue("error", "missing_card", MISSING_CARD_MESSAGE, shot_id=shot_id, card_id=cid, field="char_ids")
                )
        scene_id = row.get("scene_id")
        if scene_id and not is_none_id(scene_id) and is_scene_id(scene_id) and scene_id not in index:
            issues.append(
                issue("error", "missing_card", MISSING_CARD_MESSAGE, shot_id=shot_id, card_id=scene_id, field="scene_id")
            )
        shot_size = row.get("shot_size") or src.get("shot_size")
        if shot_size in {"CU", "ECU"} and (row.get("char_ids") or []) and not row.get("micro_expression"):
            issues.append(
                issue(
                    "warn",
                    "micro_expr_suggested",
                    "近景/特写建议填写微表情",
                    shot_id=shot_id,
                    field="micro_expression",
                )
            )
        if static_fast_conflict(camera, src.get("notes")):
            issues.append(
                issue(
                    "warn",
                    "static_fast_conflict",
                    "STATIC 与 speed:fast 冲突（继承 N2 C5）",
                    shot_id=shot_id,
                    field="camera",
                )
            )
    return issues


def raise_hard_n4(issues: list[dict[str, Any]], *, extra: dict[str, Any] | None = None) -> None:
    errors = [i for i in issues if i.get("severity") == "error"]
    if not errors:
        return
    first = errors[0]
    details: dict[str, Any] = {"issues": errors, "node": NODE_DN4}
    usable = next((i for i in errors if i.get("code") == "usable_for_n4_false"), None)
    if usable:
        missing = (usable.get("details") or {}).get("missing_refs") or []
        details["missing_refs"] = missing
        details["usable_for_n4"] = False
    if extra:
        details.update(extra)
    code = first.get("code") or "validation_failed"
    raise AppError(
        STATUS_BY_CODE.get(code, 422),
        code,
        first.get("message") or "N4 validation failed",
        messages={"zh": first.get("message") or "N4 validation failed", "en": code},
        **details,
    )
