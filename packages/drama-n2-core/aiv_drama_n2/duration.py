"""017b duration buckets + hard-adsorb (BRIEF-AIV-020 P0-B / 023 Class-D floor).

Default (tool_profile unset): snap duration_s to the dogfood tool ladder {5,8,10}
and leave tool_duration_bucket null (O9 — unset profile does not invent a bucket).

Selected tool_profile: hard-adsorb duration_s onto that profile's closed set and
write the matching bucket so duration↔bucket cannot collide.

Class-D cameras (HANDHELD/WHIP_*/ORBIT/DOLLY_ZOOM/ROLL): generate default + adsorb
floor duration_s at 8 so HANDHELD@5 / WHIP@5 cannot remain.
"""

from __future__ import annotations

from typing import Any

from aiv_drama_n2.validate import (
    BUCKET_PROFILE_PREFIX,
    CLASS_D_CAMERAS,
    CLASS_D_DURATION_FLOOR,
    TOOL_DURATION_ALLOWED,
    TOOL_DURATION_BUCKETS,
)

# Dogfood / seedance-like tool档. Used when profile is unset so generate
# still lands in {5,8,10} and later profile-select adsorb does not start from 2–3s.
DEFAULT_DURATION_LADDER = (5, 8, 10)


def allowed_durations(tool_profile: str | None) -> tuple[int, ...]:
    profile = (tool_profile or "").strip()
    if not profile:
        return DEFAULT_DURATION_LADDER
    allowed = TOOL_DURATION_ALLOWED.get(profile)
    if not allowed:
        return DEFAULT_DURATION_LADDER
    return tuple(sorted(allowed))


def nearest_duration(raw: int, allowed: tuple[int, ...]) -> int:
    if not allowed:
        return 5
    if raw in allowed:
        return raw
    # Min |delta|; ties prefer the longer bucket (019 complex moves were too short).
    return min(allowed, key=lambda value: (abs(value - raw), -value))


def is_class_d_camera(camera: Any) -> bool:
    return str(camera or "").strip().upper() in CLASS_D_CAMERAS


def class_d_allowed(allowed: tuple[int, ...]) -> tuple[int, ...]:
    floored = tuple(value for value in allowed if value >= CLASS_D_DURATION_FLOOR)
    return floored or allowed


def bucket_for(tool_profile: str | None, duration_s: int) -> str | None:
    profile = (tool_profile or "").strip()
    if not profile:
        return None
    prefix = BUCKET_PROFILE_PREFIX.get(profile)
    if not prefix:
        return None
    bucket = f"{prefix}{duration_s}"
    return bucket if bucket in TOOL_DURATION_BUCKETS else None


def adsorb_duration(
    duration_s: Any,
    tool_profile: str | None,
    camera: Any = None,
) -> tuple[int, str | None]:
    try:
        raw = int(duration_s)
    except (TypeError, ValueError):
        raw = 0
    if raw < 1:
        raw = 5
    allowed = allowed_durations(tool_profile)
    if is_class_d_camera(camera):
        allowed = class_d_allowed(allowed)
        if raw < CLASS_D_DURATION_FLOOR:
            raw = CLASS_D_DURATION_FLOOR
    snapped = nearest_duration(raw, allowed)
    return snapped, bucket_for(tool_profile, snapped)


def adsorb_row(row: dict[str, Any], tool_profile: str | None) -> dict[str, Any]:
    updated = dict(row)
    duration, bucket = adsorb_duration(
        updated.get("duration_s"),
        tool_profile,
        camera=updated.get("camera"),
    )
    updated["duration_s"] = duration
    updated["tool_duration_bucket"] = bucket
    return updated


def adsorb_rows(rows: list[dict[str, Any]], tool_profile: str | None) -> list[dict[str, Any]]:
    return [adsorb_row(row, tool_profile) for row in rows]
