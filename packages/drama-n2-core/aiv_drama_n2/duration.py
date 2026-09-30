"""D-N2 duration floors + adsorb (BRIEF-AIV-017b · FREEZE O3).

Unset ``tool_profile`` is a no-op (CONTRACT O9). Selected profile snaps
``duration_s`` to ``Allow(profile)`` at/above the CAM camera floor and
rewrites ``tool_duration_bucket`` to ``prefix:duration_s``.
"""

from __future__ import annotations

from typing import Any, NamedTuple

TOOL_PROFILES = ("seedance_2", "kling", "hailuo", "veo")
TOOL_DURATION_ALLOWED: dict[str, set[int]] = {
    "seedance_2": {5, 8, 10},
    "kling": {5, 10},
    "hailuo": {6, 10},
    "veo": {8},
}
TOOL_DURATION_BUCKETS = (
    "seedance:5",
    "seedance:8",
    "seedance:10",
    "kling:5",
    "kling:10",
    "hailuo:6",
    "hailuo:10",
    "veo:8",
)
BUCKET_SECONDS = {
    "seedance:5": 5,
    "seedance:8": 8,
    "seedance:10": 10,
    "kling:5": 5,
    "kling:10": 10,
    "hailuo:6": 6,
    "hailuo:10": 10,
    "veo:8": 8,
}
BUCKET_PROFILE_PREFIX = {
    "seedance_2": "seedance:",
    "kling": "kling:",
    "hailuo": "hailuo:",
    "veo": "veo:",
}

# CAM §3: A/B ≥5; C/D/E ≥8. Snap up to Allow(profile), never down.
CAMERA_DURATION_FLOOR: dict[str, int] = {
    "STATIC": 5,
    "POV": 5,
    "OTS": 5,
    "DEEP_FOCUS": 5,
    "PUSH": 5,
    "PULL": 5,
    "PAN_H": 5,
    "PAN_V": 5,
    "TRUCK": 5,
    "TRACK": 5,
    "CRANE_UP": 8,
    "CRANE_DOWN": 8,
    "WHIP_PUSH": 8,
    "WHIP_PULL": 8,
    "DOLLY_ZOOM": 8,
    "ROLL": 8,
    "HANDHELD": 8,
    "ORBIT": 8,
    "STATIC_TO_MOVE": 8,
}
CAMERA_FLOOR_CLASS_CDE = frozenset(
    {
        "CRANE_UP",
        "CRANE_DOWN",
        "WHIP_PUSH",
        "WHIP_PULL",
        "DOLLY_ZOOM",
        "ROLL",
        "HANDHELD",
        "ORBIT",
        "STATIC_TO_MOVE",
    }
)


class AdsorbResult(NamedTuple):
    duration_s: int
    tool_duration_bucket: str | None
    warns: list[dict[str, Any]]


def profile_selected(tool_profile: str | None) -> bool:
    return bool((tool_profile or "").strip())


def camera_duration_floor(camera: str | None) -> int | None:
    if not camera:
        return None
    return CAMERA_DURATION_FLOOR.get(str(camera))


def allowed_durations(tool_profile: str | None) -> list[int]:
    return sorted(TOOL_DURATION_ALLOWED.get(tool_profile or "", set()))


def bucket_for(tool_profile: str, duration_s: int) -> str | None:
    prefix = BUCKET_PROFILE_PREFIX.get(tool_profile)
    if not prefix:
        return None
    return f"{prefix}{int(duration_s)}"


def legal_durations_at_or_above_floor(tool_profile: str | None, camera: str | None) -> list[int]:
    allow = allowed_durations(tool_profile)
    if not allow:
        return []
    floor = camera_duration_floor(camera) or 0
    legal = [x for x in allow if x >= floor]
    return legal or [allow[-1]]


def _as_duration(raw: Any, fallback: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return fallback
    return value if value >= 1 else fallback


def _warn(
    code: str,
    message: str,
    *,
    shot_id: str | None = None,
    field: str | None = "duration_s",
    **details: Any,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "severity": "warn",
        "code": code,
        "message": message,
        "shot_id": shot_id,
        "field": field,
    }
    if details:
        out["details"] = details
    return out


def adsorb_duration_row(
    camera: str | None,
    duration_s: Any,
    tool_profile: str | None,
    *,
    shot_id: str | None = None,
) -> AdsorbResult:
    """CAM §4 adsorb. Unset profile keeps duration and clears bucket (O9)."""
    if not profile_selected(tool_profile):
        kept = _as_duration(duration_s, 5)
        return AdsorbResult(kept, None, [])

    profile = str(tool_profile).strip()
    allow = allowed_durations(profile)
    if not allow:
        kept = _as_duration(duration_s, 5)
        return AdsorbResult(kept, None, [])

    floor = camera_duration_floor(camera) or 0
    current = _as_duration(duration_s, allow[0])
    target = max(current, floor)
    candidates = [x for x in allow if x >= target]
    warns: list[dict[str, Any]] = []
    if candidates:
        duration_p = min(candidates)
    else:
        duration_p = allow[-1]
        warns.append(
            _warn(
                "duration_floor_clamped",
                "camera floor exceeds max tool bucket; clamped to max allow",
                shot_id=shot_id,
                field="duration_s",
                duration_s=current,
                adsorbed_duration_s=duration_p,
                camera=camera,
                tool_profile=profile,
                camera_floor_s=floor or None,
                allowed_duration_s=allow,
            )
        )
    bucket = bucket_for(profile, duration_p)
    return AdsorbResult(duration_p, bucket, warns)


def explicit_bucket_contradiction(row: dict[str, Any], tool_profile: str | None) -> bool:
    """True when a valid bucket of the *new* profile family disagrees with duration_s (T-V3)."""
    if not profile_selected(tool_profile):
        return False
    bucket = row.get("tool_duration_bucket")
    duration = row.get("duration_s")
    if bucket not in BUCKET_SECONDS:
        return False
    if duration == BUCKET_SECONDS[bucket]:
        return False
    prefix = BUCKET_PROFILE_PREFIX.get(str(tool_profile).strip())
    return bool(prefix and isinstance(bucket, str) and bucket.startswith(prefix))


def adsorb_storyboard_rows(
    rows: list[dict[str, Any]],
    tool_profile: str | None,
    *,
    skip_explicit_contradiction: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Adsorb every row. Unset profile is a no-op (O9).

    ``skip_explicit_contradiction`` leaves T-V3-style duration↔bucket lies
    for validate to hard-fail, so first-write mismatch still 422s.
    """
    if not profile_selected(tool_profile):
        return [dict(row) for row in rows], []

    out: list[dict[str, Any]] = []
    warns: list[dict[str, Any]] = []
    for row in rows:
        copied = dict(row)
        if skip_explicit_contradiction and explicit_bucket_contradiction(copied, tool_profile):
            out.append(copied)
            continue
        result = adsorb_duration_row(
            copied.get("camera"),
            copied.get("duration_s"),
            tool_profile,
            shot_id=copied.get("shot_id"),
        )
        copied["duration_s"] = result.duration_s
        copied["tool_duration_bucket"] = result.tool_duration_bucket
        warns.extend(result.warns)
        out.append(copied)
    return out, warns
