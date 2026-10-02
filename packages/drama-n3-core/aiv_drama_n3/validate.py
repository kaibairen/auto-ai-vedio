from __future__ import annotations

from typing import Any

from aiv_drama.errors import AppError
from aiv_drama.validate import FORCE_KEYS
from aiv_drama_n3.cards import (
    all_cards,
    has_usable_ref,
    is_char_id,
    is_none_id,
    is_scene_id,
)
from aiv_drama_n3.refs import has_must_face
from aiv_schema.models import GATE_G3, NODE_DN3

WEAK_BINDING_MESSAGE = "视觉弱绑定 · 下游一致性自负"
G3_FORCE_MESSAGE = "ForcePass=never，禁止跳过 G3"
UPSTREAM_G2_MESSAGE = "D-N2 G2 未锁定，禁止写入 D-N3"
CARDS_EMPTY_MESSAGE = "本集尚无工作副本卡；请先从 cast 物化 cards"
CAST_ONLY_MESSAGE = "卡 id 必须来自本集 cast，禁止自由发明"
IMAGE_GEN_KEYS = ("image_gen", "generate_look", "generate_image", "look_path")
IMAGE_GEN_MESSAGE = "N3 thicken 只加厚文字；禁止生图 / look 字段"


def reject_force_keys_n3(body: dict[str, Any] | None) -> None:
    if not isinstance(body, dict):
        return
    for key in FORCE_KEYS:
        if key in body:
            raise AppError(
                400,
                "force_pass_forbidden",
                G3_FORCE_MESSAGE,
                field=key,
                node=NODE_DN3,
                gate=GATE_G3,
            )


def reject_image_gen_n3(body: dict[str, Any] | None) -> None:
    if not isinstance(body, dict):
        return
    for key in IMAGE_GEN_KEYS:
        if key in body:
            raise AppError(
                400,
                "validation",
                IMAGE_GEN_MESSAGE,
                field=key,
                node=NODE_DN3,
            )


def issue(
    severity: str,
    code: str,
    message: str,
    *,
    card_id: str | None = None,
    field: str | None = None,
    **details: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "message": message,
        "card_id": card_id,
        "field": field,
    }
    if details:
        item["details"] = details
    return item


def raise_hard(issues: list[dict[str, Any]]) -> None:
    errors = [i for i in issues if i.get("severity") == "error"]
    if not errors:
        return
    first = errors[0]
    msg = first.get("message") or "N3 validation failed"
    raise AppError(
        422,
        first.get("code") or "validation",
        msg,
        messages={"zh": msg, "en": first.get("code") or "n3 validation failed"},
        issues=errors,
        node=NODE_DN3,
        gate=GATE_G3,
    )


def refs_ready_for_n4(n3: dict[str, Any] | None) -> bool:
    """Technical slot: every CHAR/SCENE card has a usable (non-provenance) ref."""
    cards = all_cards(n3)
    if not cards:
        return False
    return all(has_usable_ref(card) for card in cards)


def usable_for_n4(n3: dict[str, Any] | None, *, g3_locked: bool) -> bool:
    """Product slot. has_usable_ref does NOT imply this.

    Honest false when G3 unlocked, no cards, or any card lacks a usable ref.
    True only if the stored cards.usable_for_n4 flag is already True (挂起面).
    Attach / look / generate / G3 confirm never set that flag.
    """
    if not g3_locked:
        return False
    if not refs_ready_for_n4(n3):
        return False
    stored = ((n3 or {}).get("cards") or {}).get("usable_for_n4")
    return bool(stored)


def collect_n3_issues(
    rec: dict[str, Any],
    *,
    for_pass: bool = False,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    n3 = rec.get("n3") or {}
    cards = n3.get("cards") or {}
    characters = list(cards.get("characters") or [])
    scenes = list(cards.get("scenes") or [])
    cast = rec.get("cast") or {}
    cast_char_ids = {c.get("id") for c in (cast.get("characters") or [])}
    cast_scene_ids = {s.get("id") for s in (cast.get("scenes") or [])}

    if for_pass and not characters and not scenes:
        issues.append(issue("error", "cards_empty", CARDS_EMPTY_MESSAGE, field="cards"))

    for card in characters + scenes:
        ident = card.get("id")
        kind = card.get("kind")
        if kind == "character" and not is_char_id(ident):
            issues.append(issue("error", "card_id_not_in_cast", CAST_ONLY_MESSAGE, card_id=ident))
            continue
        if kind == "scene" and not is_scene_id(ident):
            issues.append(issue("error", "card_id_not_in_cast", CAST_ONLY_MESSAGE, card_id=ident))
            continue
        allowed = cast_char_ids if kind == "character" else cast_scene_ids
        if ident not in allowed:
            issues.append(issue("error", "card_id_not_in_cast", CAST_ONLY_MESSAGE, card_id=ident))
        if not (card.get("name") or "").strip():
            issues.append(issue("error", "card_incomplete", "卡必须有稳定称谓", card_id=ident, field="name"))
        if not (card.get("one_line") or "").strip():
            issues.append(issue("error", "card_incomplete", "卡必须有一句职司/空间功能（one_line）", card_id=ident, field="one_line"))
        if kind == "scene" and card.get("template_path"):
            issues.append(
                issue(
                    "error",
                    "invented_scene_template",
                    "禁止发明虚假 KEEP SCENE 模板路径（F2）",
                    card_id=ident,
                    field="template_path",
                    path=card.get("template_path"),
                )
            )
        if card.get("missing_ref") or not has_must_face(card) or not has_usable_ref(card):
            issues.append(
                issue(
                    "warn",
                    "missing_ref",
                    WEAK_BINDING_MESSAGE,
                    card_id=ident,
                    field="refs",
                )
            )

    # Named storyboard CHAR/SCENE must have a card (NONE excluded).
    have = {c.get("id") for c in characters + scenes}
    for row in (rec.get("storyboard") or {}).get("rows") or []:
        for cid in row.get("char_ids") or []:
            if not is_none_id(cid) and is_char_id(cid) and cid not in have:
                issues.append(
                    issue(
                        "error" if for_pass else "warn",
                        "card_missing_for_shot",
                        "分镜引用的 CHAR 缺少本集工作副本卡",
                        card_id=cid,
                        shot_id=row.get("shot_id"),
                    )
                )
        sid = row.get("scene_id")
        if not is_none_id(sid) and is_scene_id(sid) and sid not in have:
            issues.append(
                issue(
                    "error" if for_pass else "warn",
                    "card_missing_for_shot",
                    "分镜引用的 SCENE 缺少本集工作副本卡",
                    card_id=sid,
                    shot_id=row.get("shot_id"),
                )
            )

    issues.extend(
        _duplicate_name_warns(
            characters,
            code="duplicate_char_name",
            message="同集 CHAR 显示名碰撞；ID 权威，禁止静默并 ID",
        )
    )
    issues.extend(
        _duplicate_name_warns(
            scenes,
            code="duplicate_scene_name",
            message="同集 SCENE 显示名碰撞；ID 权威，禁止静默并 ID；本拍不硬挡 G3",
        )
    )
    return issues


def _duplicate_name_warns(cards: list[dict[str, Any]], *, code: str, message: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[str]] = {}
    for card in cards:
        name = (card.get("name") or "").strip()
        ident = card.get("id")
        if not name or not ident:
            continue
        buckets.setdefault(name, []).append(ident)
    out: list[dict[str, Any]] = []
    for name, ids in buckets.items():
        uniq: list[str] = []
        for ident in ids:
            if ident not in uniq:
                uniq.append(ident)
        if len(uniq) < 2:
            continue
        item = issue(
            "warn",
            code,
            message,
            card_id=uniq[0],
            field="name",
            ids=uniq,
            name=name,
        )
        item["ids"] = uniq
        item["name"] = name
        out.append(item)
    return out
