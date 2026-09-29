from __future__ import annotations

import json
import re
from typing import Any

import httpx

from aiv_drama.config import SKILL_PATHS, Settings
from aiv_drama.errors import AppError
from aiv_drama.models import GeneratedDraft
from aiv_drama.provider.fixture import FixtureProvider


class LlmProvider:
    """OpenAI-compatible chat. Falls back is not silent — missing key → provider error."""

    name = "llm"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(
        self,
        *,
        episode_id: str,
        lane: str,
        shot_cap: int,
        brief: dict[str, Any],
    ) -> GeneratedDraft:
        if not self.settings.openai_api_key:
            raise AppError(
                422,
                "provider",
                "LLM key missing; use provider=fixture or set AIV_OPENAI_API_KEY",
                node="D-N1",
            )

        skill_path = self.settings.skill_abspath(lane)
        skill_excerpt = ""
        if skill_path.is_file():
            # read-only reference; do not copy full curriculum into the package
            skill_excerpt = skill_path.read_text(encoding="utf-8")[:2000]

        prompt = {
            "episode_id": episode_id,
            "lane": lane,
            "shot_cap": shot_cap,
            "brief": {
                "title_intent": brief.get("title_intent"),
                "pin": brief.get("pin"),
                "setting_notes": brief.get("setting_notes"),
            },
            "rules": [
                "Output JSON only: body_md, characters[{name,one_line}], scenes[{name,one_line}]",
                "body_md is a 分集大纲 with 桥段序列 (numbered), 爽点/钩子, 预计镜头数上限",
                "Do NOT write 提示词, 宫格, Seedance, 分镜表, or 成稿台词",
                f"shot_cap hard cap {shot_cap}",
                "Ceiling is outline/beats only (D-N1), not D-N2",
            ],
            "skill_excerpt": skill_excerpt,
        }
        try:
            resp = httpx.post(
                f"{self.settings.openai_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                json={
                    "model": self.settings.openai_model,
                    "temperature": 0.4,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You write short-drama D-N1 outlines. JSON only.",
                        },
                        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                    ],
                },
                timeout=45.0,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            raise AppError(502, "provider", f"LLM generate failed: {exc}", node="D-N1") from exc

        parsed = _parse_llm_json(content)
        body = (parsed.get("body_md") or "").strip()
        if not body:
            # last-resort structural fixture so a flaky parse does not invent prompts
            fallback = FixtureProvider(self.settings).generate(
                episode_id=episode_id, lane=lane, shot_cap=shot_cap, brief=brief
            )
            raise AppError(502, "provider", "LLM returned empty body_md", node="D-N1", hint=fallback.body_md[:80])

        chars = parsed.get("characters") or []
        scenes = parsed.get("scenes") or []
        if not isinstance(chars, list) or not isinstance(scenes, list):
            raise AppError(502, "provider", "LLM JSON missing characters/scenes", node="D-N1")

        return GeneratedDraft(
            body_md=body + ("\n" if not body.endswith("\n") else ""),
            lane=lane,  # type: ignore[arg-type]
            shot_cap=shot_cap,
            characters=[{"name": c.get("name", ""), "one_line": c.get("one_line", "")} for c in chars],
            scenes=[{"name": s.get("name", ""), "one_line": s.get("one_line", "")} for s in scenes],
            source_skills=[SKILL_PATHS[lane]],
        )


def _parse_llm_json(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        data = json.loads(m.group(0))
        if isinstance(data, dict):
            return data
    raise AppError(502, "provider", "LLM did not return JSON", node="D-N1")
