"""N3 storyboard crop = read-only projection of existing D-N2 columns.

Does not expand D-N2 schema or rewrite G2 storyboard specs.
Reserved visible columns (PRD §3 / task): seq shot_id duration shot_size
camera action char_ids scene_id dialogue notes.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

CROP_COLUMNS = (
    "seq",
    "shot_id",
    "duration",
    "shot_size",
    "camera",
    "action",
    "char_ids",
    "scene_id",
    "dialogue",
    "notes",
)

# D-N2 SoT name for duration; crop also exposes `duration` as an alias.
N2_DURATION_FIELD = "duration_s"


def crop_row(row: dict[str, Any]) -> dict[str, Any]:
    duration = row.get(N2_DURATION_FIELD)
    return {
        "seq": row.get("seq"),
        "shot_id": row.get("shot_id"),
        "duration": duration,
        "duration_s": duration,
        "shot_size": row.get("shot_size"),
        "camera": row.get("camera"),
        "action": row.get("action"),
        "char_ids": list(row.get("char_ids") or []),
        "scene_id": row.get("scene_id"),
        "dialogue": row.get("dialogue"),
        "notes": row.get("notes"),
    }


def project_storyboard_crop(storyboard: dict[str, Any] | None) -> dict[str, Any]:
    sb = storyboard or {}
    rows = [crop_row(r) for r in sorted(sb.get("rows") or [], key=lambda r: (r.get("seq") or 0, r.get("shot_id") or ""))]
    return {
        "readonly": True,
        "source_node": "D-N2",
        "projection": "n3_crop",
        "columns": list(CROP_COLUMNS),
        "note": "裁剪=投影，≠扩 D-N2 schema；改表仍回 D-N2。B0 可无独立故事板工件。",
        "rows": rows,
        "shot_count": len(rows),
        "upstream_storyboard_version": sb.get("version") or 0,
        "storyboard_locked": bool(sb.get("locked")),
    }


def crop_view(storyboard: dict[str, Any] | None) -> dict[str, Any]:
    return deepcopy(project_storyboard_crop(storyboard))
