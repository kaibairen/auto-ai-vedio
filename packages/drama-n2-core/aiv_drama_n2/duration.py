"""017b duration buckets + hard-adsorb (BRIEF-AIV-020 P0-B).

Default (tool_profile unset): snap duration_s to the dogfood tool ladder {5,8,10}
and leave tool_duration_bucket null (O9 — unset profile does not invent a bucket).

Selected tool_profile: hard-adsorb duration_s onto that profile's closed set and
write the matching bucket so duration↔bucket cannot collide.
"""

from __future__ import annotations

from typing import Any

from aiv_drama_n2.validate import (
    BUCKET_PROFILE_PREFIX,
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


def bucket_for(tool_profile: str | None, duration_s: int) -> str | None:
    profile = (tool_profile or "").strip()
    if not profile:
        return None
    prefix = BUCKET_PROFILE_PREFIX.get(profile)
    if not prefix:
        return None
    bucket = f"{prefix}{duration_s}"
    return bucket if bucket in TOOL_DURATION_BUCKETS else None


def adsorb_duration(duration_s: Any, tool_profile: str | None) -> tuple[int, str | None]:
    try:
        raw = int(duration_s)
    except (TypeError, ValueError):
        raw = 0
    if raw < 1:
        raw = 5
    allowed = allowed_durations(tool_profile)
    snapped = nearest_duration(raw, allowed)
    return snapped, bucket_for(tool_profile, snapped)


def adsorb_row(row: dict[str, Any], tool_profile: str | None) -> dict[str, Any]:
    updated = dict(row)
    duration, bucket = adsorb_duration(updated.get("duration_s"), tool_profile)
    updated["duration_s"] = duration
    updated["tool_duration_bucket"] = bucket
    return updated


def adsorb_rows(rows: list[dict[str, Any]], tool_profile: str | None) -> list[dict[str, Any]]:
    return [adsorb_row(row, tool_profile) for row in rows]
