"""N4 hard/soft validation. ForcePass=never. Missing refs do not write jsonl."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from aiv_drama.errors import AppError
from aiv_drama.validate import FORCE_KEYS
from aiv_drama_n3.cards import all_cards, has_usable_ref, is_char_id, is_none_id, is_scene_id
from aiv_drama_n3.library import resolve_ref_file
from aiv_drama_n3.validate import usable_for_n4
from aiv_schema.models import GATE_G3, NODE_DN4

G3_FORCE_MESSAGE = "ForcePass=never，禁止跳过 D-N4 硬门"
UPSTREAM_G3_MESSAGE = "D-N3 G3 未锁定，禁止拼装 D-N4"
STALE_UPSTREAM_MESSAGE = "上游 cast/分镜/cards 已升版；请重新拼装 D-N4"
USABLE_FALSE_MESSAGE = "usable_for_n4=false · 缺图/缺 ref，拒绝写盘"
BARE_ID_MESSAGE = "prompt 禁止只留裸 CHAR-/SCENE- ID，须替换为中文特征"
EMPTY_NEGATIVE_MESSAGE = "negative 不可为空（NEG_CORE）"
STORYBOARD_EMPTY_MESSAGE = "分镜无行，无法拼装"

# From KEEP `.prompt/generation/负面提示词.md` after `--no`.
NEG_CORE = (
    "面部变形、五官扭曲、脸部拉伸、面部模糊、五官错位、多眼、少眼、歪嘴、歪鼻、下巴变形、额头变形、"
    "多手、少手、手臂重叠、肢体断裂、身体变形、比例失调、空间扭曲、透视错误、穿模、塑料感、锯齿、"
    "低清、模糊、噪点、AI artifacts、畸形、怪异、恐怖谷、非人类特征"
)

BARE_ID_RE = re.compile(r"(?:CHAR|SCENE)-\d+")


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


def collect_missing_refs(n3: dict[str, Any] | None, settings: Any | None = None) -> list[dict[str, Any]]:
    """Honest missing-image / missing-ref list. Fake path+md5 without a file is BLOCK."""
    missing: list[dict[str, Any]] = []
    for card in all_cards(n3):
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
                continue
            elif not has_usable_ref(card):
                missing.append(missing_ref_entry(card, reason="missing_ref"))
    # Dedup by (id, reason, path)
    seen: set[tuple[Any, Any, Any]] = set()
    out: list[dict[str, Any]] = []
    for item in missing:
        key = (item.get("id"), item.get("reason"), item.get("path"))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def collect_n4_issues(
    rec: dict[str, Any],
    lines: list[dict[str, Any]] | None = None,
    *,
    settings: Any | None = None,
    for_write: bool = False,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    g3_locked = bool((rec.get("gate_g3") or {}).get("locked"))
    n3 = rec.get("n3")
    cards = (n3 or {}).get("cards") or {}
    missing = collect_missing_refs(n3, settings)
    usable = usable_for_n4(n3, g3_locked=g3_locked) and not missing

    if not g3_locked:
        issues.append(issue("error", "upstream_unlocked", UPSTREAM_G3_MESSAGE, field="gate_g3"))
    if cards.get("stale"):
        issues.append(issue("error" if for_write else "warn", "stale_upstream", STALE_UPSTREAM_MESSAGE, field="cards"))
    if not (rec.get("storyboard") or {}).get("rows"):
        issues.append(issue("error", "storyboard_empty", STORYBOARD_EMPTY_MESSAGE, field="rows"))
    if not usable:
        issues.append(
            issue(
                "error",
                "usable_for_n4_false",
                USABLE_FALSE_MESSAGE,
                field="refs",
                missing_refs=missing,
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

    for row in lines or []:
        shot_id = row.get("shot_id")
        prompt = row.get("prompt") or ""
        negative = (row.get("negative") or "").strip()
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
    raise AppError(
        422,
        first.get("code") or "validation",
        first.get("message") or "N4 validation failed",
        messages={"zh": first.get("message") or "N4 validation failed", "en": first.get("code") or "n4 validation"},
        **details,
    )
