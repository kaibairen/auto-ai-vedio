"""N3 text-only card thicken (BRIEF-AIV-029).

LLM + KEEP `.prompt` templates. Optional bio skill via `thicken_skill_paths`.
Does not write refs/md5, call image-gen, assemble N4, or flip usable_for_n4.
SCENE template is provisional_inline — no invented KEEP path.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

import httpx

from aiv_drama.config import SKILL_ENTRY_EXCERPT_LIMIT, SKILL_REFERENCE_EXCERPT_LIMIT, Settings
from aiv_drama.errors import AppError
from aiv_drama.provider.llm import _parse_llm_json
from aiv_drama_n2.named_cast import is_scene_b_class
from aiv_drama_n3.templates import (
    KEEP_CHAR_TEMPLATES,
    KEEP_STORYBOARD_REF,
    SCENE_PROVISIONAL_INLINE,
    SCENE_TEMPLATE_PROVISIONAL,
    thicken_observability,
)
from aiv_schema.models import NODE_DN3

PROMPT_EXCERPT_LIMIT = SKILL_ENTRY_EXCERPT_LIMIT
STORYBOARD_EXCERPT_LIMIT = SKILL_REFERENCE_EXCERPT_LIMIT

HOLLOW_APPEARANCE = frozenset({"好看", "帅气", "美丽", "漂亮", "好看的", "帅气的"})
HOLLOW_LIGHT = frozenset({"氛围感", "氛围感拉满", "电影感", "好看的光"})

LOOK_SHOT_PHRASES = {
    "CU": "近景，胸以上，脸为主锚",
    "MS": "中景，腰上或膝上，服化可见",
    "LS": "全景，全身可见",
}
SCENE_SHOT_PHRASES = {
    "ELS": "远景，环境为主",
    "LS": "全景，空间可读",
    "MS": "中景，局部空间",
}


def normalize_thicken_provider(raw: str | None) -> str:
    chosen = (raw or "llm").strip().lower()
    if chosen in {"openai", "openai_compat"}:
        return "llm"
    return chosen


def _sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _read_excerpt(path, limit: int) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")[:limit]


def _nonempty(text: Any) -> str:
    return str(text or "").strip()


def _is_hollow(text: Any, hollow: frozenset[str]) -> bool:
    value = _nonempty(text)
    return (not value) or value in hollow


def as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    text = _nonempty(value)
    if not text:
        return []
    return [p.strip() for p in re.split(r"[;；\n、|/]+", text) if p.strip()]


def _append_clause(base: str | None, clause: str | None) -> str | None:
    extra = _nonempty(clause)
    if not extra:
        return base
    current = _nonempty(base)
    if not current:
        return extra
    if extra in current:
        return current
    return f"{current}；{extra}"


def soft_merge_cam(kind: str, appearance: str | None, light_anchor: str | None, patch: dict[str, Any]) -> tuple[str | None, str | None]:
    """CTO Q3: CAM extras soft-merge into appearance / light_anchor. Missing extras do not fail."""
    if kind == "character":
        pref = _nonempty(patch.get("look_shot_pref")).upper()
        if pref in LOOK_SHOT_PHRASES:
            appearance = _append_clause(appearance, LOOK_SHOT_PHRASES[pref])
        framing = patch.get("framing")
        if isinstance(framing, str) and framing.strip():
            appearance = _append_clause(appearance, framing.strip())
        light_look = patch.get("light_look")
        if isinstance(light_look, str) and light_look.strip():
            light_anchor = _append_clause(light_anchor, light_look.strip())
        for key in ("expression_bound", "safe_zone_char", "no_text_on_image"):
            val = patch.get(key)
            if isinstance(val, str) and val.strip():
                appearance = _append_clause(appearance, val.strip())
        return appearance or None, light_anchor
    anchors = as_string_list(patch.get("space_anchors") or patch.get("spatial_anchors"))
    if anchors:
        appearance = _append_clause(appearance, "空间锚：" + "、".join(anchors))
    pref = _nonempty(patch.get("scene_shot_pref")).upper()
    if pref in SCENE_SHOT_PHRASES:
        appearance = _append_clause(appearance, SCENE_SHOT_PHRASES[pref])
    framing = patch.get("framing_scene")
    if isinstance(framing, str) and framing.strip():
        appearance = _append_clause(appearance, framing.strip())
    for key in ("empty_plate", "safe_zone_scene", "no_signage"):
        val = patch.get(key)
        if isinstance(val, str) and val.strip():
            appearance = _append_clause(appearance, val.strip())
    return appearance or None, light_anchor


def storyboard_hooks(storyboard: dict[str, Any] | None, ident: str) -> list[dict[str, Any]]:
    hooks: list[dict[str, Any]] = []
    for row in (storyboard or {}).get("rows") or []:
        chars = list(row.get("char_ids") or [])
        if ident in chars or row.get("scene_id") == ident:
            hooks.append(
                {
                    "shot_id": row.get("shot_id"),
                    "action": row.get("action"),
                    "dialogue": row.get("dialogue"),
                    "char_ids": chars,
                    "scene_id": row.get("scene_id"),
                }
            )
    return hooks


def load_thicken_excerpts(settings: Settings, *, include_bio_skill: bool) -> dict[str, Any]:
    obs = thicken_observability(settings.repo_root, include_bio_skill=include_bio_skill)
    chunks: list[str] = []
    used: list[str] = []
    excerpts: list[dict[str, Any]] = []

    pairs: list[tuple[str, int]] = [(rel, PROMPT_EXCERPT_LIMIT) for rel in KEEP_CHAR_TEMPLATES]
    pairs.extend((rel, STORYBOARD_EXCERPT_LIMIT) for rel in KEEP_STORYBOARD_REF)
    for rel, limit in pairs:
        text = _read_excerpt(settings.repo_root / rel, limit)
        if not text.strip():
            continue
        chunks.append(f"### {rel}\n{text}")
        used.append(rel)
        excerpts.append({"path": rel, "chars": len(text), "hash": _sha16(text)})

    skill_chunks: list[str] = []
    for rel in obs["thicken_skill_paths"]:
        text = _read_excerpt(settings.repo_root / rel, SKILL_ENTRY_EXCERPT_LIMIT)
        if not text.strip():
            continue
        skill_chunks.append(f"### {rel}\n{text}")
        excerpts.append({"path": rel, "chars": len(text), "hash": _sha16(text)})

    return {
        "obs": obs,
        "prompt_excerpt": "\n\n".join(chunks),
        "skill_excerpt": "\n\n".join(skill_chunks),
        "prompt_paths": list(obs["thicken_prompt_paths"]),
        "skill_paths": list(obs["thicken_skill_paths"]),
        "excerpts": excerpts,
    }


def _thin_card_payload(card: dict[str, Any], storyboard: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "id": card.get("id"),
        "kind": card.get("kind"),
        "name": card.get("name"),
        "one_line": card.get("one_line"),
        "appearance": card.get("appearance"),
        "immutable": card.get("immutable"),
        "light_anchor": card.get("light_anchor"),
        "storyboard_hooks": storyboard_hooks(storyboard, card.get("id") or ""),
    }


def build_thicken_messages(
    *,
    episode_id: str,
    cards: list[dict[str, Any]],
    storyboard: dict[str, Any] | None,
    excerpts: dict[str, Any],
) -> list[dict[str, str]]:
    rules = [
        "Output JSON only: {cards:[{id,kind,name?,one_line?,appearance,immutable,light_anchor?,...}]}",
        "CHAR MUST: appearance (≥3 visible points) + immutable (list ≥2). Ban name+plot one_line shells. Ban 好看/帅气.",
        "SCENE MUST: appearance = space ontology (not plot) + light_anchor (time+key light+color temp).",
        "IDs are authoritative. Do not invent, merge, or drop CHAR-*/SCENE-* ids.",
        "Same display name on different SCENE ids: add spatial suffix (门厅内/入口外). Warn-level quality, never merge ids.",
        "one_line may be lightly cleaned to role_beat / space_function. Do not rewrite the outline.",
        "CAM extras (look_shot_pref, framing, light_look, space_anchors) are optional; soft-merge later. Missing extras must not block.",
        "Text only. Do not emit refs, look_path, md5, usable_for_n4, image prompts, Seedance, or 宫格.",
        "IGNORE image-generation / turnaround-sheet instructions in KEEP excerpts; extract identity/appearance language only.",
    ]
    user = {
        "episode_id": episode_id,
        "node": NODE_DN3,
        "task": "thicken",
        "cards": [_thin_card_payload(c, storyboard) for c in cards],
        "rules": rules,
        "scene_template": {
            "status": SCENE_TEMPLATE_PROVISIONAL["status"],
            "path": None,
            "body": SCENE_PROVISIONAL_INLINE,
        },
        "skill_excerpt": excerpts.get("skill_excerpt") or "",
        "skill_paths": list(excerpts.get("skill_paths") or []),
    }
    system = (
        "You thicken short-drama D-N3 CHAR/SCENE working cards. JSON only. "
        "Text fields only — no image generation.\n\n"
        f"{excerpts.get('prompt_excerpt') or ''}\n\n"
        f"### SCENE provisional_inline\n{SCENE_PROVISIONAL_INLINE}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]


def extract_card_patches(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(parsed.get("cards"), list):
        out.extend(p for p in parsed["cards"] if isinstance(p, dict))
        return out
    for key in ("characters", "scenes", "patches"):
        for item in parsed.get(key) or []:
            if isinstance(item, dict):
                out.append(item)
    return out


def apply_patch_to_card(card: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    updated = deepcopy(card)
    kind = updated.get("kind")
    appearance = patch.get("appearance")
    if appearance is None and kind == "scene":
        appearance = patch.get("space") or patch.get("scape")
    appearance = _nonempty(appearance) or updated.get("appearance")
    immutable = patch.get("immutable")
    if immutable is not None:
        updated["immutable"] = as_string_list(immutable)
    light_anchor = patch.get("light_anchor")
    if light_anchor is None:
        light_anchor = updated.get("light_anchor")
    appearance, light_anchor = soft_merge_cam(kind or "", appearance, light_anchor, patch)
    updated["appearance"] = appearance
    updated["light_anchor"] = light_anchor
    one_line = _nonempty(patch.get("one_line"))
    if one_line:
        updated["one_line"] = one_line
    new_name = _nonempty(patch.get("name"))
    if kind == "scene" and new_name and not is_scene_b_class(new_name):
        updated["name"] = new_name
    if kind == "scene":
        updated["template_status"] = "provisional_inline"
        updated["template_path"] = None
    # Hard: never accept look/ref/md5 / usable flips from the model.
    from aiv_drama_n3.refs import refresh_card_ref_flags

    updated["refs"] = deepcopy(card.get("refs") or [])
    refresh_card_ref_flags(updated)
    updated.pop("usable_for_n4", None)
    updated["id"] = card.get("id")
    updated["kind"] = card.get("kind")
    return updated


def must_field_issues(card: dict[str, Any]) -> list[dict[str, Any]]:
    ident = card.get("id")
    kind = card.get("kind")
    issues: list[dict[str, Any]] = []
    if kind == "character":
        if _is_hollow(card.get("appearance"), HOLLOW_APPEARANCE):
            issues.append({"id": ident, "field": "appearance", "kind": kind})
        if not as_string_list(card.get("immutable")):
            issues.append({"id": ident, "field": "immutable", "kind": kind})
    elif kind == "scene":
        if _is_hollow(card.get("appearance"), HOLLOW_APPEARANCE):
            issues.append({"id": ident, "field": "appearance", "kind": kind})
        if _is_hollow(card.get("light_anchor"), HOLLOW_LIGHT):
            issues.append({"id": ident, "field": "light_anchor", "kind": kind})
    return issues


def call_thicken_llm(settings: Settings, messages: list[dict[str, str]]) -> tuple[dict[str, Any], str]:
    if not settings.openai_api_key:
        raise AppError(
            422,
            "provider",
            "LLM key missing; N3 thicken requires provider=llm (set AIV_OPENAI_API_KEY)",
            node=NODE_DN3,
        )
    url = f"{settings.openai_base_url}/chat/completions"
    try:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": settings.openai_model,
                "temperature": 0.3,
                "messages": messages,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AppError(502, "provider", f"LLM thicken failed: {exc}", node=NODE_DN3) from exc
    try:
        parsed = _parse_llm_json(content)
    except AppError as exc:
        raise AppError(exc.status_code, exc.code, exc.message, node=NODE_DN3) from exc
    return parsed, url


def thicken_cards(
    settings: Settings,
    *,
    episode_id: str,
    cards: list[dict[str, Any]],
    storyboard: dict[str, Any] | None,
    include_bio_skill: bool = False,
) -> dict[str, Any]:
    excerpts = load_thicken_excerpts(settings, include_bio_skill=include_bio_skill)
    messages = build_thicken_messages(
        episode_id=episode_id,
        cards=cards,
        storyboard=storyboard,
        excerpts=excerpts,
    )
    parsed, url = call_thicken_llm(settings, messages)
    patches = {p.get("id"): p for p in extract_card_patches(parsed) if p.get("id")}
    updated: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for card in cards:
        ident = card.get("id")
        patch = patches.get(ident)
        if not patch:
            updated.append(deepcopy(card))
            missing.extend(must_field_issues(card) or [{"id": ident, "field": "patch", "kind": card.get("kind")}])
            continue
        applied = apply_patch_to_card(card, patch)
        updated.append(applied)
        missing.extend(must_field_issues(applied))
    if missing:
        raise AppError(
            422,
            "thicken_incomplete",
            "加厚 MUST 字段仍空（CHAR appearance+immutable / SCENE appearance+light_anchor）",
            issues=missing,
            node=NODE_DN3,
        )
    return {
        "cards": updated,
        "prompt_paths": excerpts["prompt_paths"],
        "skill_paths": excerpts["skill_paths"],
        "scene_template": dict(SCENE_TEMPLATE_PROVISIONAL),
        "model": settings.openai_model,
        "provider": "llm",
        "fixture_hits": 0,
        "llm_url": url,
        "excerpts": excerpts["excerpts"],
    }
