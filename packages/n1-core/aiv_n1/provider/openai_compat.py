from __future__ import annotations

import json
from typing import Any

import httpx

from aiv_n1.config import Settings
from aiv_n1.errors import AppError
from aiv_n1.provider.base import GenerateRequest, GenerateResponse
from aiv_n1.provider.fixture import FixtureProvider
from aiv_n1.validate import CHAR_LIMIT, draft_chars


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        if not self.settings.openai_api_key:
            raise AppError(400, "provider", "AIV_OPENAI_API_KEY is empty")
        user = {
            "path": req.path,
            "step": req.step,
            "kind": req.kind,
            "raw": req.raw,
            "notes": req.notes,
            "frameworks": req.frameworks,
            "char_limit": CHAR_LIMIT[req.path],
        }
        payload = {
            "model": self.settings.openai_model,
            "temperature": 0.4,
            "messages": [
                {
                    "role": "system",
                    "content": "N1 koubo step engine. Reply with one JSON object.\n\n"
                    + (req.prompt_text[:12000] if req.prompt_text else ""),
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
                content = res.json()["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            raise AppError(502, "provider", f"openai-compatible call failed: {exc}") from exc
        parsed = _extract_json(content)
        if parsed is None:
            return FixtureProvider().generate(req)
        return _from_parsed(req, parsed)


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
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
            title = str(c.get("title") or "")
            body = str(c.get("body") or "")
            cleaned.append(
                {
                    "id": c.get("id") or f"c{i + 1}",
                    "title": title,
                    "body": body,
                    "chars": draft_chars(title, body),
                    "framework": str(c.get("framework") or ""),
                }
            )
        candidates = cleaned
    titles = data.get("titles")
    if isinstance(titles, list):
        out = []
        for i, t in enumerate(titles[:3]):
            if isinstance(t, dict):
                out.append({"id": t.get("id") or f"t{i + 1}", "title": str(t.get("title") or "")})
            else:
                out.append({"id": f"t{i + 1}", "title": str(t)})
        titles = out
    return GenerateResponse(
        kind=str(data.get("kind") or req.kind),
        message=str(data.get("message") or ""),
        extract=data.get("extract") if isinstance(data.get("extract"), dict) else None,
        frameworks=list(data.get("frameworks") or []) or None,
        candidates=candidates,
        titles=titles,
        draft_title=data.get("draft_title"),
        draft_body=data.get("draft_body"),
    )
