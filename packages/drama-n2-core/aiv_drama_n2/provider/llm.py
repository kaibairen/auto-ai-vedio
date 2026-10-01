from __future__ import annotations

import json
import unicodedata
from typing import Any

import httpx

from aiv_drama.config import Settings
from aiv_drama.errors import AppError
from aiv_drama.provider.llm import _parse_llm_json
from aiv_drama_n2.duration import adsorb_duration
from aiv_drama_n2.skill_evidence import STORYBOARD_GUIDE_PATH, excerpt_borrowed_dongman
from aiv_drama_n2.validate import (
    CAMERAS,
    SEEDANCE_SKILL_PATH,
    STORYBOARD_SKILL_PATH,
    extract_bridge_ids,
    normalize_row,
    text_has_prompt,
)
from aiv_schema.models import NODE_DN2

SHOT_SIZE_ALIASES = {
    "ELS": "ELS",
    "LS": "LS",
    "MS": "MS",
    "CU": "CU",
    "ECU": "ECU",
    "远景": "ELS",
    "远": "ELS",
    "全景": "LS",
    "全": "LS",
    "中景": "MS",
    "中": "MS",
    "近景": "CU",
    "近": "CU",
    "特写": "ECU",
}

CAMERA_ALIASES = {
    **{code: code for code in CAMERAS},
    "固定": "STATIC",
    "主观": "POV",
    "手持": "HANDHELD",
    "过肩": "OTS",
    "深焦": "DEEP_FOCUS",
    "推": "PUSH",
    "推镜头": "PUSH",
    "拉": "PULL",
    "拉镜头": "PULL",
    "水平摇": "PAN_H",
    "横摇": "PAN_H",
    "垂直摇": "PAN_V",
    "移": "TRUCK",
    "跟": "TRACK",
    "跟镜头": "TRACK",
    "升": "CRANE_UP",
    "降": "CRANE_DOWN",
    "环绕": "ORBIT",
    "旋转": "ROLL",
    "滑动变焦": "DOLLY_ZOOM",
    "急推": "WHIP_PUSH",
    "急拉": "WHIP_PULL",
    "静动转换": "STATIC_TO_MOVE",
}


def _norm_name(name: str) -> str:
    text = unicodedata.normalize("NFKC", (name or "").strip())
    return " ".join(text.split())


class LlmStoryboardProvider:
    """OpenAI-compatible chat for D-N2 storyboard. Missing key → provider error (no silent fixture)."""

    name = "llm"
    skill_relpath = STORYBOARD_SKILL_PATH

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(
        self,
        *,
        episode_id: str,
        outline: dict[str, Any],
        cast: dict[str, Any],
        shot_cap: int,
        tool_profile: str | None,
    ) -> list[dict[str, Any]]:
        if not self.settings.openai_api_key:
            raise AppError(
                422,
                "provider",
                "LLM key missing; use provider=fixture or set AIV_OPENAI_API_KEY",
                node=NODE_DN2,
            )

        skill_excerpt, skill_paths, _excerpts = excerpt_borrowed_dongman(self.settings)
        if any(SEEDANCE_SKILL_PATH in p for p in skill_paths):
            raise AppError(422, "provider", "Seedance 出片 Skill must not be injected", node=NODE_DN2)

        chars = [c for c in (cast.get("characters") or []) if isinstance(c, dict) and c.get("id")]
        scenes = [s for s in (cast.get("scenes") or []) if isinstance(s, dict) and s.get("id")]
        bridges = extract_bridge_ids(outline.get("body_md") or "")
        prompt = {
            "episode_id": episode_id,
            "node": NODE_DN2,
            "shot_cap": shot_cap,
            "tool_profile": tool_profile,
            "storyboard_skill": "borrowed_dongman",
            "outline": {
                "lane": outline.get("lane"),
                "shot_cap": outline.get("shot_cap"),
                "body_md": outline.get("body_md"),
                "version": outline.get("version"),
            },
            "cast": {
                "characters": [
                    {"id": c.get("id"), "name": c.get("name"), "one_line": c.get("one_line")} for c in chars
                ],
                "scenes": [
                    {"id": s.get("id"), "name": s.get("name"), "one_line": s.get("one_line")} for s in scenes
                ],
            },
            "bridge_ids": bridges,
            "rules": [
                "Output JSON only: {rows:[...]}",
                "Each row: shot_id, bridge_id, seq, duration_s, shot_size, camera, action, char_ids, scene_id, dialogue, transition, dynamic_level, tool_duration_bucket, grid_strict, notes",
                "bridge_id is required (B1, B2, … from outline 桥段); one bridge may have many shots",
                f"1 ≤ rows.length ≤ {shot_cap} (hard cap 12)",
                "shot_size English only: ELS|LS|MS|CU|ECU",
                "camera English only, one primary move: STATIC|POV|HANDHELD|OTS|DEEP_FOCUS|PUSH|PULL|PAN_H|PAN_V|TRUCK|TRACK|CRANE_UP|CRANE_DOWN|ORBIT|ROLL|DOLLY_ZOOM|WHIP_PUSH|WHIP_PULL|STATIC_TO_MOVE",
                "char_ids must be locked cast CHAR-* ids, or NONE / [] for empty/crowd",
                "scene_id must be locked SCENE-* or NONE",
                "Fold names onto locked cast ids; do not invent CHAR/SCENE ids",
                "action/dialogue must not introduce named speakers or action agents absent from cast.characters[].name; weaken unknowns to UI/系统音 or use only given cast names",
                "Group labels (王子们 / 两位王子) must expand to already-listed CHAR ids; do not invent a group CHAR",
                "系统音 / 弹窗字 / 旁白 / 广播 without a character-name speaker prefix are OK and must NOT become CHAR names",
                "Never invent CHAR from 【系统音】/半截广播台词/半截对白切片/句级叙述碎片/动词短语/脏前缀 (leading /). Ban names like 你被双王子 / 而是两王子 / 王国王子 / AI王子 / 两侧王子 / 豆包当众拆穿两个王子 / 包的开源权重反制两个闭源王子 / 吐槽两位王子 / 技术王子 / 幕里两位王子 / 两位王子 / 幕里…王子 / 正统王子 / 体验王子 / 重构王子 / 回滚王子 / 弹窗王子 / 破防王子 / 联猎王子 / 拆穿两位王子 / 吐槽程序员 / 弹幕里两位王子 / 屏幕里两位王子 / 最优解 / 最贵解 / 联猎 / 非技术型AI / 代码库已冻结 / 倒计时开始. Collection 两王子/双王子/两侧王子/指出两王子/幕里两位王子 expand to GPT王子 + Opus5.5王子 or GPT(CODEX)王子 + Opus5.5(CURSOR)王子 (or CODEX王子 + CURSOR(Opus5.5)王子), never as their own CHAR. Bare brands CURSOR/CODEX/GPT fold onto Opus5.5王子/GPT王子 — never open a bare-brand CHAR. Bare 王子 folds onto existing 03/04. Keep 程序员 / 豆包 / GPT(CODEX)王子 / Opus5.5(CURSOR)王子. Parenthesis wraps like CURSOR（Opus5.5王子） are one entity, not two rows. NAME slot only: outline/one_line prose 技术王子/两位王子/回滚王子 is allowed description and must not delete ALLOW rows",
                "duration_s must be one of 5, 8, or 10 (dogfood tool档). Prefer 5 dialogue CU, 8 action, 10 complex camera. Do not emit 2s/3s/4s",
                "Class-D cameras HANDHELD/WHIP_PUSH/WHIP_PULL/ORBIT/DOLLY_ZOOM/ROLL must use duration_s ≥ 8 (default 8; never 5). On the same row as any Class-D camera write duration_s 8 or 10 — never 5",
                "Rotate Class-D kinds (closed set WHIP_PUSH|WHIP_PULL|DOLLY_ZOOM|ROLL|HANDHELD|ORBIT). Beat hooks: climax/dual-window → WHIP_PUSH or WHIP_PULL; look-around break → ORBIT; chase/oppression → HANDHELD; identity/perspective warp → DOLLY_ZOOM; system collapse → ROLL. Do not count PUSH/PULL/CRANE_*/STATIC_TO_MOVE as Class-D",
                "SHOULD density on ~12-shot boards: ≥5 Class-D shots, ≥4 distinct Class-D kinds, spread across ≥2 beats; one kind ≤ ceil(D_count/2). Missing density is a self-check rewrite, not a hard FAIL. Do not copy one camera to fake count",
                "If tool_profile is set, duration_s must be in that profile's closed set and tool_duration_bucket must match the same seconds (no collision)",
                "If tool_profile is empty, leave tool_duration_bucket null; still use duration_s ∈ {5,8,10}",
                "action/dialogue/notes are short intent only — no 提示词, 宫格, Seedance, [ImageN], 时间轴, or full outpaint prompts",
                "No prompt / negative_prompt / seedance_* / outpaint_* fields",
                "angle/camera_speed go in notes as angle: / speed: prefixes",
                "Do not write D-N3 cards or N4 prompts",
            ],
            "skill_excerpt": skill_excerpt,
            "skill_paths": skill_paths,
        }
        try:
            resp = httpx.post(
                f"{self.settings.openai_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                json={
                    "model": self.settings.openai_model,
                    "temperature": 0.3,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You write short-drama D-N2 storyboard tables. JSON only. Isolated from koubo-N1.",
                        },
                        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                    ],
                },
                timeout=45.0,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AppError(502, "provider", f"LLM generate failed: {exc}", node=NODE_DN2) from exc

        try:
            parsed = _parse_llm_json(content)
        except AppError as exc:
            raise AppError(exc.status_code, exc.code, exc.message, node=NODE_DN2) from exc
        raw_rows = parsed.get("rows")
        if not isinstance(raw_rows, list) or not raw_rows:
            raise AppError(502, "provider", "LLM JSON missing rows[]", node=NODE_DN2)

        rows = _normalize_llm_rows(
            raw_rows,
            shot_cap=shot_cap,
            cast_chars=chars,
            cast_scenes=scenes,
            bridges=bridges,
            tool_profile=tool_profile,
        )
        if not rows:
            raise AppError(502, "provider", "LLM returned no usable storyboard rows", node=NODE_DN2)
        return rows


def _normalize_llm_rows(
    raw_rows: list[Any],
    *,
    shot_cap: int,
    cast_chars: list[dict[str, Any]],
    cast_scenes: list[dict[str, Any]],
    bridges: list[str],
    tool_profile: str | None,
) -> list[dict[str, Any]]:
    cap = min(int(shot_cap), 12)
    char_by_id = {str(c["id"]): c for c in cast_chars}
    char_by_name = {}
    for c in cast_chars:
        key = _norm_name(str(c.get("name") or ""))
        if key and key not in char_by_name:
            char_by_name[key] = str(c["id"])
    scene_by_id = {str(s["id"]): s for s in cast_scenes}
    scene_by_name = {}
    for s in cast_scenes:
        key = _norm_name(str(s.get("name") or ""))
        if key and key not in scene_by_name:
            scene_by_name[key] = str(s["id"])

    out: list[dict[str, Any]] = []
    for i, raw in enumerate(raw_rows[:cap], start=1):
        if not isinstance(raw, dict):
            continue
        for field in ("action", "dialogue", "notes", "transition"):
            if text_has_prompt(raw.get(field)):
                raise AppError(
                    422,
                    "prompt_forbidden",
                    "full generation prompts forbidden in storyboard",
                    field=field,
                    shot_id=raw.get("shot_id") or f"S{i:02d}",
                    node=NODE_DN2,
                )
        payload = dict(raw)
        payload["shot_size"] = _alias_cam(payload.get("shot_size"), SHOT_SIZE_ALIASES)
        payload["camera"] = _alias_cam(payload.get("camera"), CAMERA_ALIASES)
        payload["char_ids"] = _fold_char_ids(payload.get("char_ids"), char_by_id, char_by_name)
        payload["scene_id"] = _fold_scene_id(payload.get("scene_id"), scene_by_id, scene_by_name)
        if not (payload.get("bridge_id") or "").strip():
            payload["bridge_id"] = bridges[min(i - 1, len(bridges) - 1)] if bridges else ""
        payload["seq"] = i
        payload["shot_id"] = f"S{i:02d}"
        duration, bucket = adsorb_duration(
            _coerce_duration(payload.get("duration_s")),
            tool_profile,
            camera=payload.get("camera"),
        )
        payload["duration_s"] = duration
        payload["tool_duration_bucket"] = bucket
        row = normalize_row(payload, index=i)
        out.append(row)
    return out


def _alias_cam(raw: Any, table: dict[str, str]) -> Any:
    key = str(raw or "").strip()
    if key in table:
        return table[key]
    folded = key.upper().replace("-", "_").replace(" ", "_")
    return table.get(folded, raw)


def _coerce_duration(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 5
    return value if value >= 1 else 5


def _fold_char_ids(raw: Any, by_id: dict[str, Any], by_name: dict[str, str]) -> list[str]:
    if raw is None or raw == "":
        return ["NONE"]
    if isinstance(raw, str):
        items = [p.strip() for p in raw.replace("|", ";").split(";") if p.strip()]
    elif isinstance(raw, list):
        items = [str(x).strip() for x in raw if str(x).strip()]
    else:
        items = [str(raw).strip()]
    if not items or items == ["NONE"]:
        return ["NONE"]
    folded: list[str] = []
    for item in items:
        if item == "NONE":
            if "NONE" not in folded:
                folded.append("NONE")
            continue
        if item in by_id:
            if item not in folded:
                folded.append(item)
            continue
        name_key = _norm_name(item)
        mapped = by_name.get(name_key)
        if mapped and mapped not in folded:
            folded.append(mapped)
            continue
        if item not in folded:
            folded.append(item)
    if folded == ["NONE"]:
        return ["NONE"]
    return [c for c in folded if c != "NONE"] or folded


def _fold_scene_id(raw: Any, by_id: dict[str, Any], by_name: dict[str, str]) -> str:
    value = ("" if raw is None else str(raw)).strip()
    if not value or value == "NONE":
        return "NONE"
    if value in by_id:
        return value
    mapped = by_name.get(_norm_name(value))
    return mapped or value
