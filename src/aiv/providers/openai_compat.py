from __future__ import annotations

import json
from typing import Any

import httpx

from aiv.config import Settings
from aiv.curriculum import CHAR_LIMIT, TITLE_LIMIT_B
from aiv.errors import AppError
from aiv.providers.base import GenerateRequest, GenerateResponse
from aiv.providers.fixture import FixtureProvider
from aiv.validation import count_chars


class OpenAICompatProvider:
    """Optional OpenAI-compatible chat provider. Falls back is not used here."""

    name = "openai"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        if not self.settings.openai_api_key:
            raise AppError(400, "llm_unconfigured", "AIV_OPENAI_API_KEY is empty")
        schema_hint = {
            "kind": "ack|analysis|frameworks|candidates|titles|draft",
            "message": "string",
            "analysis": {"core_points": [], "keywords": [], "logic": "", "golden": ""},
            "frameworks": ["name"],
            "titles": ["<=20 chars"],
            "candidates": [{"index": 0, "title": "", "body": "", "framework": ""}],
            "draft_title": "",
            "draft_body": "",
        }
        user = {
            "path": req.path,
            "step": req.step,
            "kind": req.kind,
            "notes": req.notes,
            "frameworks": req.frameworks,
            "titles": req.titles,
            "pick": req.pick,
            "title": req.title,
            "char_limit": CHAR_LIMIT[req.path],
            "title_limit_if_B": TITLE_LIMIT_B if req.path == "B" else None,
            "raw": req.raw,
            "analysis": req.analysis,
            "return_json": schema_hint,
            "rules": [
                "一步只做当前 step，不要一次输出后续步骤",
                "忠于原料，不虚构",
                "口播前 3 秒给钩子，结尾只留一个主 CTA",
            ],
        }
        payload = {
            "model": self.settings.openai_model,
            "temperature": 0.4,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the N1 koubo step engine. Follow the curriculum prompt. "
                        "Reply with a single JSON object only.\n\n"
                        + (req.prompt_text[:12000] if req.prompt_text else "")
                    ),
                },
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
        }
        try:
            with httpx.Client(timeout=60.0) as client:
                res = client.post(
                    f"{self.settings.openai_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.settings.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                res.raise_for_status()
                data = res.json()
                content = data["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001 — surface vendor failure
            raise AppError(502, "llm_failed", f"openai-compatible call failed: {exc}") from exc

        parsed = _extract_json(content)
        if parsed is None:
            # Keep the session usable: wrap as message, then fixture-shape draft if needed.
            fallback = FixtureProvider().generate(req)
            fallback.message = content.strip()[:2000] or fallback.message
            fallback.extra["provider_parse"] = "fallback_fixture_shape"
            return fallback
        return _from_parsed(req, parsed)


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start : end + 1])
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
        return None


def _from_parsed(req: GenerateRequest, data: dict[str, Any]) -> GenerateResponse:
    limit = CHAR_LIMIT[req.path]
    candidates = data.get("candidates")
    if isinstance(candidates, list):
        cleaned = []
        for i, c in enumerate(candidates):
            if not isinstance(c, dict):
                continue
            body = str(c.get("body") or "")
            if count_chars(body) > limit:
                body = body[: limit * 2]
            cleaned.append(
                {
                    "index": i,
                    "title": str(c.get("title") or ""),
                    "body": body,
                    "chars": count_chars(body),
                    "framework": str(c.get("framework") or ""),
                }
            )
        candidates = cleaned
    titles = data.get("titles")
    if isinstance(titles, list):
        titles = [str(t) for t in titles][:3]
    return GenerateResponse(
        kind=str(data.get("kind") or req.kind),
        message=str(data.get("message") or ""),
        analysis=data.get("analysis") if isinstance(data.get("analysis"), dict) else None,
        frameworks=list(data.get("frameworks") or []) or None,
        candidates=candidates,
        titles=titles,
        draft_title=data.get("draft_title"),
        draft_body=data.get("draft_body"),
        extra={"provider": "openai"},
    )
