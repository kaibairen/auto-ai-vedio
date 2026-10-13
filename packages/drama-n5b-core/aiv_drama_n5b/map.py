"""N4 jsonl → Ark Seedance 2.0 task body. SCOUT §3–§4. No HTTP."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from aiv_drama.errors import AppError
from aiv_drama_n5b.constants import (
    ALLOWED_DURATIONS,
    ASPECT_TO_RATIO,
    DEFAULT_RESOLUTION,
    MAX_REF_IMAGES,
    NEGATIVE_JOIN,
    SEEDANCE_SKU_PRIMARY,
    TOOL_PROFILE_REQUIRED,
)
from aiv_schema.models import NODE_DN5B


def map_aspect(aspect: str | None) -> str:
    raw = (aspect or "").strip()
    if raw not in ASPECT_TO_RATIO:
        raise AppError(
            422,
            "validation",
            "aspect 须为 9:16 / 16:9 / 2.35:1（→21:9）",
            node=NODE_DN5B,
            aspect=raw,
        )
    return ASPECT_TO_RATIO[raw]


def map_duration(duration_s: Any) -> int:
    try:
        value = int(duration_s)
    except (TypeError, ValueError):
        value = 0
    if value not in ALLOWED_DURATIONS:
        raise AppError(
            422,
            "duration_out_of_profile",
            "duration_s 须落入 seedance_2 档 {5,8,10}",
            node=NODE_DN5B,
            duration_s=duration_s,
        )
    return value


def compose_text(prompt: str | None, negative: str | None = None) -> str:
    text = (prompt or "").strip()
    neg = (negative or "").strip()
    if not text:
        raise AppError(422, "validation", "prompt 不能为空", node=NODE_DN5B, field="prompt")
    if neg:
        return f"{text}{NEGATIVE_JOIN}{neg}"
    return text


def _is_hosted_url(value: str) -> bool:
    raw = (value or "").strip()
    if raw.startswith(("data:", "asset://")):
        return True
    parsed = urlparse(raw)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def map_ref_images(refs: list[Any] | None, *, max_refs: int = MAX_REF_IMAGES) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Each jsonl ref → image_url + role=reference_image. Local paths stay local (not hosted)."""
    items: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []
    for raw in refs or []:
        if isinstance(raw, dict):
            url = str(raw.get("url") or raw.get("path") or "").strip()
            role = str(raw.get("role") or "reference_image").strip() or "reference_image"
        else:
            url = str(raw or "").strip()
            role = "reference_image"
        if not url:
            continue
        hosted = _is_hosted_url(url)
        items.append({"type": "image_url", "image_url": {"url": url}, "role": role})
        notes.append({"url": url, "hosted": hosted, "role": role})
        if len(items) >= max_refs:
            break
    return items, notes


def jsonl_to_content(line: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    content: list[dict[str, Any]] = [{"type": "text", "text": compose_text(line.get("prompt"), line.get("negative"))}]
    images, notes = map_ref_images(line.get("ref_images"))
    content.extend(images)
    return content, notes


def map_jsonl_line_to_task_body(
    line: dict[str, Any],
    *,
    model: str | None = None,
    resolution: str = DEFAULT_RESOLUTION,
) -> dict[str, Any]:
    profile = (line.get("tool_profile") or TOOL_PROFILE_REQUIRED).strip()
    if profile not in {TOOL_PROFILE_REQUIRED, "seedance_2_0"}:
        raise AppError(
            422,
            "unsupported_tool_profile",
            "N5b 只映射 seedance_2（N4 闭集）",
            node=NODE_DN5B,
            tool_profile=profile,
        )
    content, _notes = jsonl_to_content(line)
    sku = (model or line.get("SKU") or line.get("sku") or SEEDANCE_SKU_PRIMARY).strip()
    body: dict[str, Any] = {
        "model": sku,
        "content": content,
        "duration": map_duration(line.get("duration_s")),
        "ratio": map_aspect(line.get("aspect")),
        "resolution": resolution,
        "watermark": False,
        "generate_audio": False,
    }
    seed = line.get("seed")
    if seed is not None:
        body["seed"] = seed
    else:
        body["seed"] = None
    return body


def map_jsonl_lines(
    lines: list[dict[str, Any]],
    *,
    shot_id: str | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    wanted = (shot_id or "").strip() or None
    out: list[dict[str, Any]] = []
    for line in lines:
        sid = (line.get("shot_id") or "").strip()
        if wanted and sid != wanted:
            continue
        content, ref_notes = jsonl_to_content(line)
        body = map_jsonl_line_to_task_body(line, model=model)
        out.append(
            {
                "shot_id": sid,
                "body": body,
                "content": content,
                "ratio": body["ratio"],
                "duration": body["duration"],
                "SKU": body["model"],
                "tool_profile": TOOL_PROFILE_REQUIRED,
                "ref_notes": ref_notes,
                "ref_needs_hosting": any(not n.get("hosted") for n in ref_notes),
                "clip_relpath": f"clips/{sid}.mp4" if sid else None,
                "meta_relpath": f"clips/{sid}.meta.json" if sid else None,
            }
        )
    if wanted and not out:
        raise AppError(404, "not_found", "shot_id 不在 EP##-prompts.jsonl", node=NODE_DN5B, shot_id=wanted)
    return out
