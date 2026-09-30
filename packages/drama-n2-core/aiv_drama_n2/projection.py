from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import yaml

from aiv_drama.skill_trace import excerpt_projection
from aiv_drama.store import atomic_write_text
from aiv_schema.models import NODE_DN2

CSV_COLUMNS = (
    "shot_id",
    "bridge_id",
    "duration_s",
    "shot_size",
    "camera",
    "action",
    "char_ids",
    "scene_id",
    "dialogue",
    "transition",
    "dynamic_level",
    "tool_duration_bucket",
    "grid_strict",
    "notes",
)


def _join_chars(char_ids: Any) -> str:
    if not char_ids:
        return ""
    return ";".join(str(c) for c in char_ids)


def write_storyboard_csv(episode_dir: Path, ep: str, storyboard: dict[str, Any]) -> Path:
    path = episode_dir / f"{ep}-分镜.csv"
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(CSV_COLUMNS), extrasaction="ignore")
    writer.writeheader()
    rows = sorted(storyboard.get("rows") or [], key=lambda r: (r.get("seq") or 0, r.get("shot_id") or ""))
    for row in rows:
        writer.writerow(
            {
                "shot_id": row.get("shot_id") or "",
                "bridge_id": row.get("bridge_id") or "",
                "duration_s": row.get("duration_s") if row.get("duration_s") is not None else "",
                "shot_size": row.get("shot_size") or "",
                "camera": row.get("camera") or "",
                "action": row.get("action") or "",
                "char_ids": _join_chars(row.get("char_ids")),
                "scene_id": row.get("scene_id") or "",
                "dialogue": row.get("dialogue") or "",
                "transition": row.get("transition") or "",
                "dynamic_level": row.get("dynamic_level") or "",
                "tool_duration_bucket": row.get("tool_duration_bucket") or "",
                "grid_strict": "true" if row.get("grid_strict") else "false",
                "notes": row.get("notes") or "",
            }
        )
    text = buf.getvalue()
    if not text.endswith("\n"):
        text += "\n"
    atomic_write_text(path, text)
    return path


def write_storyboard_md(episode_dir: Path, ep: str, storyboard: dict[str, Any]) -> Path:
    path = episode_dir / f"{ep}-分镜.md"
    rows = sorted(storyboard.get("rows") or [], key=lambda r: (r.get("seq") or 0, r.get("shot_id") or ""))
    fm = [
        "---",
        f"node: {NODE_DN2}",
        f"episode_id: {storyboard.get('episode_id') or ep}",
        "pipeline_profile: drama",
        f"lane: {storyboard.get('lane')}",
        f"version: {storyboard.get('version')}",
        f"locked: {str(bool(storyboard.get('locked'))).lower()}",
        f"confirmed_by: {storyboard.get('confirmed_by')}",
        f"shot_cap: {storyboard.get('shot_cap')}",
        f"shot_count: {storyboard.get('shot_count')}",
        f"storyboard_skill: {storyboard.get('storyboard_skill')}",
        f"tool_profile: {storyboard.get('tool_profile')}",
        f"stale: {str(bool(storyboard.get('stale'))).lower()}",
        f"ready_for_n4: {str(bool(storyboard.get('ready_for_n4'))).lower()}",
        f"upstream_outline_version: {storyboard.get('upstream_outline_version')}",
        f"upstream_cast_version: {storyboard.get('upstream_cast_version')}",
    ]
    skill_block = yaml.safe_dump(
        {
            "skill_paths": list(storyboard.get("skill_paths") or []),
            "skill_trace": storyboard.get("skill_trace") or "none",
            "skill_trace_reason": storyboard.get("skill_trace_reason"),
            "excerpts": excerpt_projection(storyboard.get("excerpts") or [], include_text=False),
        },
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).rstrip()
    fm.extend(skill_block.splitlines())
    fm.extend(
        [
            "---",
            "",
            f"# {ep} 分镜",
            "",
            "机读权威在 API/DB；本文件为人读投影。景别/运镜为 CAM 英文短码（O7）。",
            "",
        ]
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row.get("bridge_id") or "?", []).append(row)
    if not rows:
        fm.append("_（空表）_")
        fm.append("")
    else:
        for bridge, group in grouped.items():
            fm.append(f"## {bridge}")
            fm.append("")
            fm.append("| shot_id | seq | duration_s | shot_size | camera | action | char_ids | scene_id | dialogue | notes |")
            fm.append("|---|---:|---:|---|---|---|---|---|---|---|")
            for row in group:
                chars = _join_chars(row.get("char_ids"))
                action = (row.get("action") or "").replace("|", "/")
                dialogue = (row.get("dialogue") or "").replace("|", "/")
                notes = (row.get("notes") or "").replace("|", "/")
                fm.append(
                    f"| {row.get('shot_id')} | {row.get('seq')} | {row.get('duration_s')} | "
                    f"{row.get('shot_size')} | {row.get('camera')} | {action} | {chars} | "
                    f"{row.get('scene_id')} | {dialogue} | {notes} |"
                )
            fm.append("")
    text = "\n".join(fm)
    if not text.endswith("\n"):
        text += "\n"
    atomic_write_text(path, text)
    return path
