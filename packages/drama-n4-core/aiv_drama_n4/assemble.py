"""Deterministic per-shot prompt assembly. No LLM."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from aiv_drama_n3.cards import is_char_id, is_none_id, is_scene_id
from aiv_drama_n3.char_look import reviewed_look_sheet_path
from aiv_drama_n4.camera import camera_lex, safe_zone_note, shot_size_lex
from aiv_drama_n4.id_resolve import card_features, card_index, card_version, feature_catalog, replace_ids
from aiv_drama_n4.skeleton import EMPTY_SUBJECT, SLOT_REF_LEAD, SKELETON_ID, SKELETON_VERSION
from aiv_drama_n4.tools import lookup_adapter
from aiv_drama_n4.validate import NEG_CORE


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _ref_images(
    char_cards: list[dict[str, Any]],
    scene_card: dict[str, Any] | None,
    *,
    n3: dict[str, Any] | None = None,
) -> list[str]:
    """CAM §6: char_ids order, then scene plate. Mode B may use reviewed 合板 path.

    Never invent paths. Face/full refs stay first; sheet is a fallback, not a fake face.
    """
    seen: set[str] = set()
    out: list[str] = []
    for card in [*char_cards, scene_card]:
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
        sheet = reviewed_look_sheet_path(card, n3)
        if sheet and sheet not in seen:
            seen.add(sheet)
            out.append(sheet)
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


def _scene_card(row: dict[str, Any], index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    scene_id = row.get("scene_id")
    if not scene_id or is_none_id(scene_id) or not is_scene_id(scene_id):
        return None
    return index.get(scene_id)


def _light_mood(scene_card: dict[str, Any] | None, row: dict[str, Any]) -> str:
    """Use card light_anchor or notes light:* — never invent 平光."""
    if scene_card:
        light = _text(scene_card.get("light_anchor"))
        if light:
            return light
    notes = _text(row.get("notes"))
    for token in notes.replace(",", " ").split():
        if token.lower().startswith("light:"):
            return token.split(":", 1)[1].strip()
    return ""


def _bound_char_ids(row: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for cid in row.get("char_ids") or []:
        if is_none_id(cid) or not is_char_id(cid):
            continue
        out.append(cid)
    return out


def card_fingerprint(card_versions: dict[str, Any]) -> str:
    raw = json.dumps(card_versions, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def g2_fingerprint(rec: dict[str, Any]) -> str:
    sb = rec.get("storyboard") or {}
    payload = {
        "version": sb.get("version") or 0,
        "tool_profile": sb.get("tool_profile"),
        "rows": [
            {
                "shot_id": row.get("shot_id"),
                "duration_s": row.get("duration_s"),
                "camera": row.get("camera"),
                "shot_size": row.get("shot_size"),
                "action": row.get("action"),
                "char_ids": row.get("char_ids"),
                "scene_id": row.get("scene_id"),
            }
            for row in (sb.get("rows") or [])
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
    adapter = lookup_adapter(tool_profile) or lookup_adapter("seedance_2")
    if adapter is None:
        raise RuntimeError("seedance_2 adapter missing")
    duration = int(row.get("duration_s") or 0)
    bound_ids = _bound_char_ids(row)
    char_cards = _char_cards(row, index)
    scene_card = _scene_card(row, index)
    scene_id = row.get("scene_id")

    subject_blocks = [card_features(card, kind="character") for card in char_cards]
    subject_blocks = [block for block in subject_blocks if block]
    if not bound_ids:
        subject = EMPTY_SUBJECT
    else:
        subject = "；".join(subject_blocks)

    scene = card_features(scene_card, kind="scene") if scene_card else ""
    action = replace_ids(_text(row.get("action")), catalog)
    light = replace_ids(_light_mood(scene_card, row), catalog)
    notes = row.get("notes")
    parts = {
        "slot_ref_lead": SLOT_REF_LEAD,
        "slot_subject_blocks": subject,
        "slot_scene_anchor": scene,
        "slot_light_mood": light,
        "slot_action": action,
        "slot_micro_expr": "",
        "slot_shot_size_lex": shot_size_lex(row.get("shot_size")),
        "slot_camera_lex": camera_lex(row.get("camera"), notes=notes),
        "slot_duration_hint": f"约{duration}秒" if duration else "",
    }
    zone = safe_zone_note(row.get("shot_size"), aspect)
    prompt = adapter.format_prompt(parts, extra_tail=zone or None)
    prompt = replace_ids(prompt, catalog)
    negative = adapter.format_negative(NEG_CORE)

    char_ids = [cid for cid in bound_ids]
    char_versions = {cid: card_version(index.get(cid)) for cid in char_ids}
    versions: dict[str, Any] = {
        cid: {
            "binding": (index.get(cid) or {}).get("binding"),
            "version": char_versions.get(cid),
            "origin": (index.get(cid) or {}).get("origin"),
        }
        for cid in char_ids
    }
    if scene_card and scene_card.get("id"):
        versions[scene_card["id"]] = {
            "binding": scene_card.get("binding"),
            "version": card_version(scene_card),
            "origin": scene_card.get("origin"),
        }
    elif scene_id and not is_none_id(scene_id) and is_scene_id(scene_id):
        versions[scene_id] = {"binding": None, "version": None, "origin": None}

    line: dict[str, Any] = {
        "shot_id": row.get("shot_id"),
        "duration_s": duration,
        "aspect": aspect,
        "tool_profile": tool_profile,
        "prompt": prompt,
        "negative": negative,
        "ref_images": _ref_images(char_cards, scene_card),
        "camera": row.get("camera"),
        "shot_size": row.get("shot_size"),
        "char_ids": char_ids,
        "scene_id": scene_card.get("id") if scene_card else (scene_id if scene_id and not is_none_id(scene_id) else None),
        "char_versions": char_versions,
        "scene_version": card_version(scene_card),
        "card_versions": versions,
        "card_fingerprint": card_fingerprint(versions),
        "cards_version": cards_version,
        "assemble_version": assemble_version,
        "skeleton_id": SKELETON_ID,
        "skeleton_version": SKELETON_VERSION,
        "safe_zone_note": zone or None,
        "micro_expression": None,
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
        "card_fingerprint": line.get("card_fingerprint"),
        "cards_version": line.get("cards_version"),
        "assemble_version": line.get("assemble_version"),
        "skeleton_id": line.get("skeleton_id"),
        "g2_fingerprint": line.get("g2_fingerprint"),
        "storyboard_version": line.get("storyboard_version"),
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
    sb = rec.get("storyboard") or {}
    extra = {
        "storyboard_version": sb.get("version") or 0,
        "g2_fingerprint": g2_fingerprint(rec),
    }
    rows = list(sb.get("rows") or [])
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
            extra=extra,
        )
        for row in rows
    ]
