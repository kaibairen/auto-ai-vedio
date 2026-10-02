"""Assemble a single-sheet grid image prompt from N4 jsonl (not LLM)."""

from __future__ import annotations

from typing import Any

from aiv_drama_n5a.exempt import scene_look_exempt

GRID_PROMPT_PATHS = {
    9: ".prompt/generation/宫格-9.md",
    16: ".prompt/generation/宫格-16.md",
}

_NEG = (
    "no timecode, no subtitles, no readable garbled text, no colorbars, "
    "no UI overlay, no watermark block, no extra people, no deformed hands"
)


def _clip(text: Any, limit: int = 180) -> str:
    value = " ".join(str(text or "").split()).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def select_lines(lines: list[dict[str, Any]], *, shots: list[str] | None, layout: int) -> list[dict[str, Any]]:
    chosen = list(lines)
    wanted = [s.strip() for s in (shots or []) if s and s.strip()]
    if wanted:
        index = {row.get("shot_id"): row for row in lines}
        chosen = [index[sid] for sid in wanted if sid in index]
        if not chosen:
            chosen = list(lines)
    if not chosen:
        return []
    if len(chosen) >= layout:
        return chosen[:layout]
    padded = list(chosen)
    while len(padded) < layout:
        padded.append(chosen[-1])
    return padded


def assemble_grid_prompt(
    rec: dict[str, Any],
    lines: list[dict[str, Any]],
    *,
    layout: int,
) -> str:
    rows = 3 if layout == 9 else 4
    cols = rows
    ep = rec["episode"]["episode_id"]
    exempt = scene_look_exempt(rec, ep)
    scene_note = (
        "SCENE-LOOK-EXEMPT: location may vary; do not require a locked scene plate."
        if exempt
        else "Keep scene space logic consistent across cells when a scene card exists."
    )
    header = [
        f"Output ONE photoreal cinematic {rows}x{cols} storyboard grid ({layout} panels) as a single image.",
        "Same character identity, wardrobe, and hairstyle in every cell. No face-swap.",
        scene_note,
        "Clean gutters, no panel labels, no readable in-image text.",
        _NEG,
        "",
    ]
    body: list[str] = []
    for i, row in enumerate(lines, start=1):
        shot = row.get("shot_id") or f"S{i:02d}"
        size = row.get("shot_size") or ""
        camera = row.get("camera") or ""
        prompt = _clip(row.get("prompt"), 220)
        body.append(f"Panel {i} [{shot}] {size} {camera}: {prompt}".strip())
    text = "\n".join(header + body) + "\n"
    if len(text) > 3800:
        text = text[:3799].rstrip() + "\n"
    return text
