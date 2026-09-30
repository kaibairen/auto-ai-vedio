from __future__ import annotations

import re
from typing import Any

from aiv_drama.config import SHOT_CAP_HARD
from aiv_drama.errors import AppError
from aiv_drama.validate import FORCE_KEYS
from aiv_schema.models import GATE_G2, NODE_DN2

SHOT_SIZES = ("ELS", "LS", "MS", "CU", "ECU")
SHOT_RANK = {"ELS": 0, "LS": 1, "MS": 2, "CU": 3, "ECU": 4}

CAMERAS = (
    "STATIC",
    "POV",
    "HANDHELD",
    "OTS",
    "DEEP_FOCUS",
    "PUSH",
    "PULL",
    "PAN_H",
    "PAN_V",
    "TRUCK",
    "TRACK",
    "CRANE_UP",
    "CRANE_DOWN",
    "ORBIT",
    "ROLL",
    "DOLLY_ZOOM",
    "WHIP_PUSH",
    "WHIP_PULL",
    "STATIC_TO_MOVE",
)

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

SHOT_ID_RE = re.compile(r"^S\d{2,}$")
NONE_ID = "NONE"

FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "prompt",
        "negative_prompt",
        "grid_prompt",
        "outpaint_prompt",
        "seedance_prompt",
    }
)
FORBIDDEN_FIELD_PREFIXES = ("seedance_", "outpaint_")

PROMPT_MARKERS = (
    "宫格",
    "提示词",
    "seedance",
    "[imagen",
    "负面提示词",
    "9宫格",
    "16宫格",
    "25宫格",
    "[image1]",
    "[image2]",
    "[image3]",
    "[image4]",
    "[image5]",
    "检g1",
    "检 g1",
    "negative_prompt",
    "outpaint",
    "grid_prompt",
    "时间轴",
    "0-5s",
    "0-5 s",
    "0–5s",
    "complete prompt",
)

COMPLEX_CAMERAS = frozenset({"WHIP_PUSH", "WHIP_PULL", "DOLLY_ZOOM", "ROLL", "HANDHELD", "ORBIT"})
STORYBOARD_SKILL_PATH = ".skill/writing/动态漫-转分镜/SKILL.md"
SEEDANCE_SKILL_PATH = ".skill/generation/Seedance2.0-分镜"


def reject_force_keys_n2(body: dict[str, Any] | None) -> None:
    if not isinstance(body, dict):
        return
    for key in FORCE_KEYS:
        if key in body:
            raise AppError(
                400,
                "force_pass_forbidden",
                "ForcePass=never",
                field=key,
                node=NODE_DN2,
                gate=GATE_G2,
            )


def reject_prompt_fields(raw: dict[str, Any] | None) -> None:
    """Reject prompt / Seedance / outpaint columns anywhere in a write body."""
    if not isinstance(raw, dict):
        return
    _reject_prompt_keys(raw, shot_id=None)
    for row in raw.get("rows") or []:
        if isinstance(row, dict):
            _reject_prompt_keys(row, shot_id=row.get("shot_id"))


def _reject_prompt_keys(obj: dict[str, Any], *, shot_id: str | None) -> None:
    for key in obj:
        lowered = str(key).lower()
        if lowered in FORBIDDEN_FIELD_NAMES or lowered.startswith(FORBIDDEN_FIELD_PREFIXES):
            raise AppError(
                422,
                "prompt_forbidden",
                "full generation prompts forbidden in storyboard",
                field=key,
                shot_id=shot_id,
                node=NODE_DN2,
            )


def text_has_prompt(value: Any) -> bool:
    text = (value or "")
    if not isinstance(text, str):
        return False
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in PROMPT_MARKERS)


def reject_prompt_text(*, shot_id: str | None, field: str, value: Any) -> None:
    if text_has_prompt(value):
        raise AppError(
            422,
            "prompt_forbidden",
            "full generation prompts forbidden in storyboard",
            field=field,
            shot_id=shot_id,
            node=NODE_DN2,
        )


def issue(
    severity: str,
    code: str,
    message: str,
    *,
    shot_id: str | None = None,
    field: str | None = None,
    **details: Any,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "message": message,
        "shot_id": shot_id,
        "field": field,
    }
    if details:
        out["details"] = details
    return out


def inherit_shot_cap(outline_cap: Any, override: int | None = None) -> int:
    cap = SHOT_CAP_HARD if outline_cap is None else int(outline_cap)
    if override is not None:
        cap = min(cap, int(override))
    if cap < 1:
        raise AppError(422, "validation", "shot_cap must be >= 1", node=NODE_DN2)
    if cap > SHOT_CAP_HARD:
        raise AppError(
            422,
            "shot_cap_exceeded",
            "rows exceed shot_cap",
            shot_cap=SHOT_CAP_HARD,
            requested=cap,
            node=NODE_DN2,
        )
    return cap


def extract_bridge_ids(body_md: str) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"^\s*(\d+)\s*[\.、\)]\s+\S+", body_md or "", re.M):
        ident = f"B{int(match.group(1))}"
        if ident not in seen:
            seen.add(ident)
            ids.append(ident)
    return ids


def _named_char(ident: str) -> bool:
    return bool(ident) and ident != NONE_ID


def _named_scene(ident: str) -> bool:
    return bool(ident) and ident != NONE_ID


def collect_issues(
    rows: list[dict[str, Any]],
    *,
    shot_cap: int,
    tool_profile: str | None,
    cast: dict[str, Any] | None,
    outline_body: str | None = None,
    for_pass: bool = False,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    known_chars = {c.get("id") for c in ((cast or {}).get("characters") or []) if c.get("id")}
    known_scenes = {s.get("id") for s in ((cast or {}).get("scenes") or []) if s.get("id")}

    if for_pass and not rows:
        issues.append(issue("error", "storyboard_empty", "pass requires at least one shot"))
        return issues
    if len(rows) > shot_cap or len(rows) > SHOT_CAP_HARD:
        issues.append(
            issue(
                "error",
                "shot_cap_exceeded",
                "rows exceed shot_cap",
                shot_cap=shot_cap,
                row_count=len(rows),
            )
        )

    seen_ids: set[str] = set()
    seen_seq: set[int] = set()
    prev_size: str | None = None
    prev_shot: str | None = None
    covered: set[str] = set()

    for idx, row in enumerate(rows):
        shot_id = row.get("shot_id") or f"S{idx + 1:02d}"
        for field in ("action", "dialogue", "notes", "transition", "dynamic_level"):
            if text_has_prompt(row.get(field)):
                issues.append(
                    issue(
                        "error",
                        "prompt_forbidden",
                        "full generation prompts forbidden in storyboard",
                        shot_id=shot_id,
                        field=field,
                    )
                )

        if not SHOT_ID_RE.match(str(shot_id)):
            issues.append(issue("error", "validation", "shot_id must match ^S\\d{2,}$", shot_id=shot_id, field="shot_id"))
        if shot_id in seen_ids:
            issues.append(issue("error", "shot_id_duplicate", "shot_id must be unique", shot_id=shot_id, field="shot_id"))
        seen_ids.add(shot_id)

        seq = row.get("seq")
        if not isinstance(seq, int) or seq < 1:
            issues.append(issue("error", "seq_invalid", "seq must be an integer >= 1", shot_id=shot_id, field="seq"))
        elif seq in seen_seq:
            issues.append(issue("error", "seq_invalid", "seq must be unique", shot_id=shot_id, field="seq", seq=seq))
        else:
            seen_seq.add(seq)

        bridge = (row.get("bridge_id") or "").strip()
        if not bridge:
            issues.append(issue("error", "bridge_id_missing", "bridge_id is required", shot_id=shot_id, field="bridge_id"))
        else:
            covered.add(bridge)

        size = row.get("shot_size")
        if size not in SHOT_SIZES:
            issues.append(
                issue(
                    "error",
                    "cam_enum_invalid",
                    "shot_size/camera not in CAM closed set",
                    shot_id=shot_id,
                    field="shot_size",
                    value=size,
                )
            )
        camera = row.get("camera")
        if camera not in CAMERAS:
            issues.append(
                issue(
                    "error",
                    "cam_enum_invalid",
                    "shot_size/camera not in CAM closed set",
                    shot_id=shot_id,
                    field="camera",
                    value=camera,
                )
            )
        elif isinstance(camera, str) and ("+" in camera or "|" in camera or " " in camera.strip()):
            issues.append(
                issue(
                    "error",
                    "cam_enum_invalid",
                    "one primary camera move per shot",
                    shot_id=shot_id,
                    field="camera",
                    value=camera,
                )
            )

        action = (row.get("action") or "").strip()
        if not action:
            issues.append(
                issue("error", "storyboard_incomplete", "action is required", shot_id=shot_id, field="action")
            )

        char_ids = row.get("char_ids")
        if not isinstance(char_ids, list):
            issues.append(issue("error", "validation", "char_ids must be an array", shot_id=shot_id, field="char_ids"))
            char_ids = []
        named_chars = [c for c in char_ids if _named_char(str(c))]
        if not char_ids or char_ids == [NONE_ID]:
            notes = (row.get("notes") or "").strip()
            if not notes:
                issues.append(
                    issue(
                        "warn",
                        "none_notes_suggested",
                        "NONE / empty char_ids should explain empty/crowd in notes (O5)",
                        shot_id=shot_id,
                        field="notes",
                    )
                )
        for cid in named_chars:
            if cid not in known_chars:
                issues.append(
                    issue(
                        "error",
                        "cast_id_unknown",
                        "named CHAR/SCENE not in locked cast",
                        shot_id=shot_id,
                        field="char_ids",
                        id=cid,
                    )
                )

        scene_id = row.get("scene_id")
        if not scene_id:
            issues.append(issue("error", "storyboard_incomplete", "scene_id is required", shot_id=shot_id, field="scene_id"))
        elif _named_scene(str(scene_id)) and scene_id not in known_scenes:
            issues.append(
                issue(
                    "error",
                    "cast_id_unknown",
                    "named CHAR/SCENE not in locked cast",
                    shot_id=shot_id,
                    field="scene_id",
                    id=scene_id,
                )
            )

        duration = row.get("duration_s")
        bucket = row.get("tool_duration_bucket")
        if bucket is not None and bucket not in TOOL_DURATION_BUCKETS:
            issues.append(
                issue(
                    "error",
                    "duration_bucket_mismatch",
                    "duration_s not in tool_duration_bucket",
                    shot_id=shot_id,
                    field="tool_duration_bucket",
                    duration_s=duration,
                    tool_duration_bucket=bucket,
                )
            )
        elif tool_profile and bucket:
            expected = BUCKET_SECONDS.get(bucket)
            prefix = BUCKET_PROFILE_PREFIX.get(tool_profile)
            if expected is not None and duration != expected:
                issues.append(
                    issue(
                        "error",
                        "duration_bucket_mismatch",
                        "duration_s not in tool_duration_bucket",
                        shot_id=shot_id,
                        field="duration_s",
                        duration_s=duration,
                        tool_duration_bucket=bucket,
                    )
                )
            if prefix and isinstance(bucket, str) and not bucket.startswith(prefix):
                issues.append(
                    issue(
                        "error",
                        "duration_bucket_mismatch",
                        "duration_s not in tool_duration_bucket",
                        shot_id=shot_id,
                        field="tool_duration_bucket",
                        duration_s=duration,
                        tool_duration_bucket=bucket,
                    )
                )
        elif tool_profile and duration not in TOOL_DURATION_ALLOWED.get(tool_profile, set()):
            issues.append(
                issue(
                    "error",
                    "duration_bucket_mismatch",
                    "duration_s not in tool_duration_bucket",
                    shot_id=shot_id,
                    field="duration_s",
                    duration_s=duration,
                    tool_profile=tool_profile,
                )
            )
        elif not tool_profile:
            if bucket:
                issues.append(
                    issue(
                        "warn",
                        "tool_profile_unset",
                        "tool_profile empty; duration/bucket not blocking G2; ready_for_n4 stays false (O9)",
                        shot_id=shot_id,
                        field="tool_profile",
                    )
                )

        if size in SHOT_RANK and prev_size in SHOT_RANK:
            jump = abs(SHOT_RANK[size] - SHOT_RANK[prev_size])
            transition = (row.get("transition") or "").strip()
            notes = (row.get("notes") or "").strip()
            if jump > 2:
                issues.append(
                    issue(
                        "warn",
                        "shot_size_jump_j1",
                        "adjacent shot_size jump exceeds 2 levels (J1)",
                        shot_id=shot_id,
                        field="shot_size",
                        from_shot=prev_shot,
                        from_size=prev_size,
                        to_size=size,
                    )
                )
            if jump >= 3 and not transition and not notes:
                issues.append(
                    issue(
                        "warn",
                        "shot_size_jump_j2",
                        "jump ≥3 levels should set transition or notes (J2)",
                        shot_id=shot_id,
                        field="transition",
                        from_shot=prev_shot,
                        from_size=prev_size,
                        to_size=size,
                    )
                )
        prev_size = size if size in SHOT_RANK else prev_size
        prev_shot = shot_id

        suggest_grid = (
            size in {"CU", "ECU"}
            or len(named_chars) >= 2
            or camera in COMPLEX_CAMERAS
            or (row.get("dynamic_level") or "") == "特效"
        )
        if suggest_grid and not row.get("grid_strict"):
            issues.append(
                issue(
                    "warn",
                    "grid_strict_suggested",
                    "complex shot should set grid_strict=true (G2-C5 soft)",
                    shot_id=shot_id,
                    field="grid_strict",
                )
            )
        notes = row.get("notes") or ""
        if camera == "STATIC" and "speed:fast" in notes.replace(" ", ""):
            issues.append(
                issue(
                    "warn",
                    "static_speed_fast",
                    "STATIC should not pair with speed:fast (C5)",
                    shot_id=shot_id,
                    field="notes",
                )
            )

    if not tool_profile:
        issues.append(
            issue(
                "warn",
                "tool_profile_unset",
                "tool_profile empty does not block G2; ready_for_n4 must stay false (O9)",
                field="tool_profile",
            )
        )

    bridges = extract_bridge_ids(outline_body or "")
    if bridges:
        missing = [b for b in bridges if b not in covered]
        # last two numbered bridges ≈ 主爽 / 集尾钩 when outline has ≥4 beats
        critical = bridges[-2:] if len(bridges) >= 4 else []
        critical_missing = [b for b in critical if b not in covered]
        if critical_missing:
            issues.append(
                issue(
                    "warn",
                    "bridge_uncovered",
                    "climax/ending-hook bridges have 0 shots (G2-D3; warn, human gate)",
                    field="bridge_id",
                    missing=critical_missing,
                )
            )
        elif missing:
            issues.append(
                issue(
                    "warn",
                    "bridge_uncovered",
                    "some outline bridges have 0 shots",
                    field="bridge_id",
                    missing=missing,
                )
            )

    return issues


def first_hard_error(issues: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((i for i in issues if i.get("severity") == "error"), None)


def raise_hard(issues: list[dict[str, Any]]) -> None:
    hard = first_hard_error(issues)
    if not hard:
        return
    details = dict(hard.get("details") or {})
    if hard.get("shot_id"):
        details.setdefault("shot_id", hard["shot_id"])
    if hard.get("field"):
        details.setdefault("field", hard["field"])
    raise AppError(422, hard["code"], hard["message"], **details)


def ready_for_n4(tool_profile: str | None, issues: list[dict[str, Any]]) -> bool:
    if not tool_profile:
        return False
    return first_hard_error(issues) is None


def normalize_row(raw: dict[str, Any], *, index: int) -> dict[str, Any]:
    shot_id = raw.get("shot_id") or f"S{index:02d}"
    char_ids = raw.get("char_ids")
    if not isinstance(char_ids, list):
        char_ids = []
    return {
        "shot_id": shot_id,
        "bridge_id": (raw.get("bridge_id") or "").strip(),
        "seq": int(raw.get("seq") or index),
        "duration_s": int(raw.get("duration_s") or 0),
        "shot_size": raw.get("shot_size"),
        "camera": raw.get("camera"),
        "action": raw.get("action") or "",
        "char_ids": [str(c) for c in char_ids],
        "scene_id": raw.get("scene_id") or "",
        "dialogue": raw.get("dialogue"),
        "transition": raw.get("transition"),
        "dynamic_level": raw.get("dynamic_level"),
        "tool_duration_bucket": raw.get("tool_duration_bucket"),
        "grid_strict": bool(raw.get("grid_strict") or False),
        "notes": raw.get("notes"),
    }
