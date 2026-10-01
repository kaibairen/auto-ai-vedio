"""Deterministic per-shot prompt assembly. No LLM."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from aiv_drama_n3.cards import all_cards, is_char_id, is_none_id, is_scene_id
from aiv_drama_n4.camera import camera_slot
from aiv_drama_n4.skeleton import (
    DEFAULT_LIGHT,
    DEFAULT_STYLE,
    EMPTY_SCENE,
    EMPTY_SUBJECT,
    SKELETON_ID,
    SKELETON_VERSION,
    render_slots,
)
from aiv_drama_n4.validate import NEG_CORE, BARE_ID_RE

FALLBACK_CHAR = "未写明外貌的角色"
FALLBACK_SCENE = "未写明空间特征的场景"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def card_features(card: dict[str, Any] | None, *, kind: str) -> str:
    """ID → 中文特征. Never return a bare CHAR-/SCENE- id."""
    if not card:
        return FALLBACK_CHAR if kind == "character" else FALLBACK_SCENE
    name = _text(card.get("name"))
    one_line = _text(card.get("one_line"))
    appearance = card.get("appearance")
    extra = ""
    if isinstance(appearance, dict):
        extra = "，".join(_text(v) for v in appearance.values() if _text(v))
    elif appearance is not None:
        extra = _text(appearance)
    parts = [p for p in (name, one_line, extra) if p and not BARE_ID_RE.fullmatch(p)]
    if not parts:
        return FALLBACK_CHAR if kind == "character" else FALLBACK_SCENE
    return "，".join(dict.fromkeys(parts))


def card_index(n3: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in all_cards(n3) if c.get("id")}


def feature_catalog(n3: dict[str, Any] | None) -> dict[str, str]:
    catalog: dict[str, str] = {}
    for card in all_cards(n3):
        ident = card.get("id")
        if not ident:
            continue
        kind = "character" if is_char_id(ident) else "scene"
        catalog[ident] = card_features(card, kind=kind)
    return catalog


def replace_ids(text: str, catalog: dict[str, str]) -> str:
    def _repl(match: re.Match[str]) -> str:
        ident = match.group(0)
        return catalog.get(ident) or catalog.get(ident.upper()) or ident

    return BARE_ID_RE.sub(_repl, text or "")


def assert_no_bare_ids(text: str) -> bool:
    return BARE_ID_RE.search(text or "") is None


def _card_version(card: dict[str, Any] | None) -> int | None:
    if not card:
        return None
    lib = card.get("library_ref") or {}
    if isinstance(lib, dict) and lib.get("version") is not None:
        try:
            return int(lib["version"])
        except (TypeError, ValueError):
            return None
    return None


def _ref_images(cards: list[dict[str, Any] | None]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for card in cards:
        if not card:
            continue
        for ref in card.get("refs") or []:
            if not isinstance(ref, dict):
                continue
            path = _text(ref.get("path"))
            if not path or path in seen:
                continue
            seen.add(path)
            out.append(path)
    return out


def _char_cards(row: dict[str, Any], index: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for cid in row.get("char_ids") or []:
        if is_none_id(cid) or not is_char_id(cid):
            continue
        card = index.get(cid)
        if card:
            cards.append(card)
    return cards


def assemble_shot(
    row: dict[str, Any],
    *,
    index: dict[str, dict[str, Any]],
    catalog: dict[str, str],
    aspect: str,
    tool_profile: str,
    cards_version: int,
    assemble_version: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    duration = int(row.get("duration_s") or 0)
    char_cards = _char_cards(row, index)
    scene_id = row.get("scene_id")
    scene_card = index.get(scene_id) if scene_id and not is_none_id(scene_id) and is_scene_id(scene_id) else None

    subject = "；".join(card_features(c, kind="character") for c in char_cards) or EMPTY_SUBJECT
    scene = card_features(scene_card, kind="scene") if scene_card else EMPTY_SCENE
    action = replace_ids(_text(row.get("action")), catalog)
    dialogue_raw = _text(row.get("dialogue"))
    dialogue = replace_ids(dialogue_raw, catalog) if dialogue_raw else ""
    light_src = (scene_card or {}).get("light_anchor") if scene_card else None
    light = replace_ids(_text(light_src) or DEFAULT_LIGHT, catalog)

    prompt = render_slots(
        {
            "style": f"{DEFAULT_STYLE}，{duration}秒，画幅{aspect}",
            "subject": subject,
            "scene": scene,
            "action": action,
            "camera": camera_slot(row.get("shot_size"), row.get("camera")),
            "light": light,
            "dialogue": dialogue,
        }
    )
    prompt = replace_ids(prompt, catalog)

    char_ids = [c.get("id") for c in char_cards if c.get("id")]
    char_versions = {cid: _card_version(index.get(cid)) for cid in char_ids}
    card_versions = {
        cid: {
            "binding": (index.get(cid) or {}).get("binding"),
            "version": char_versions.get(cid),
            "origin": (index.get(cid) or {}).get("origin"),
        }
        for cid in char_ids
    }
    if scene_card and scene_card.get("id"):
        card_versions[scene_card["id"]] = {
            "binding": scene_card.get("binding"),
            "version": _card_version(scene_card),
            "origin": scene_card.get("origin"),
        }

    line: dict[str, Any] = {
        "shot_id": row.get("shot_id"),
        "duration_s": duration,
        "aspect": aspect,
        "tool_profile": tool_profile,
        "prompt": prompt,
        "negative": NEG_CORE,
        "ref_images": _ref_images([*char_cards, scene_card]),
        "camera": row.get("camera"),
        "shot_size": row.get("shot_size"),
        "char_ids": char_ids,
        "scene_id": scene_card.get("id") if scene_card else (scene_id if scene_id and not is_none_id(scene_id) else None),
        "char_versions": char_versions,
        "scene_version": _card_version(scene_card),
        "card_versions": card_versions,
        "cards_version": cards_version,
        "assemble_version": assemble_version,
        "skeleton_id": SKELETON_ID,
        "skeleton_version": SKELETON_VERSION,
    }
    if extra:
        line.update(extra)
    line["fingerprint"] = line_fingerprint(line)
    return line


def line_fingerprint(line: dict[str, Any]) -> str:
    payload = {
        "shot_id": line.get("shot_id"),
        "prompt": line.get("prompt"),
        "negative": line.get("negative"),
        "tool_profile": line.get("tool_profile"),
        "aspect": line.get("aspect"),
        "camera": line.get("camera"),
        "char_ids": line.get("char_ids"),
        "scene_id": line.get("scene_id"),
        "card_versions": line.get("card_versions"),
        "cards_version": line.get("cards_version"),
        "assemble_version": line.get("assemble_version"),
        "skeleton_id": line.get("skeleton_id"),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def assemble_fingerprint(lines: list[dict[str, Any]], *, meta: dict[str, Any]) -> str:
    payload = {
        "skeleton_id": SKELETON_ID,
        "skeleton_version": SKELETON_VERSION,
        "meta": meta,
        "lines": [
            {
                "shot_id": row.get("shot_id"),
                "fingerprint": row.get("fingerprint"),
                "prompt": row.get("prompt"),
                "negative": row.get("negative"),
            }
            for row in lines
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def assemble_episode_lines(
    rec: dict[str, Any],
    *,
    tool_profile: str,
    aspect: str,
    assemble_version: int,
) -> list[dict[str, Any]]:
    n3 = rec.get("n3")
    index = card_index(n3)
    catalog = feature_catalog(n3)
    cards_version = int(((n3 or {}).get("cards") or {}).get("version") or 0)
    rows = list((rec.get("storyboard") or {}).get("rows") or [])
    rows = sorted(rows, key=lambda r: (r.get("seq") or 0, r.get("shot_id") or ""))
    return [
        assemble_shot(
            row,
            index=index,
            catalog=catalog,
            aspect=aspect,
            tool_profile=tool_profile,
            cards_version=cards_version,
            assemble_version=assemble_version,
        )
        for row in rows
    ]
