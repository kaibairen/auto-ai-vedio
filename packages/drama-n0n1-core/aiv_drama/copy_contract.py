"""018d COPY-CONTRACT: ErrorCode catalog, bilingual messages, thin raise sites.

SoT for code ↔ zh/en. Handlers raise via ``raise_hard`` / ``evaluate`` /
``enforce_intent_for_generate``. docs≠PASS; ForcePass=never.
"""

from __future__ import annotations

import re
from typing import Any

from aiv_drama.errors import AppError

# ----- HTTP ErrorCode (must be raised by a handler) ---------------------------------

N0N1_ERROR_CODES: frozenset[str] = frozenset(
    {
        "validation",
        "not_found",
        "conflict",
        "locked",
        "upstream_unlocked",
        "downstream_locked",
        "version_conflict",
        "lane_required",
        "outline_empty",
        "outline_contains_prompts",
        "shot_cap_exceeded",
        "brief_incomplete",
        "intent_unconfirmed",
        "intent_stale",
        "intent_lane_conflict",
        "cast_incomplete",
        "episode_abandoned",
        "force_pass_forbidden",
        "provider",
        "library_ref_unresolved",
    }
)

N2_ERROR_CODES: frozenset[str] = frozenset(
    {
        "named_cast_gate",
        "named_cast_missing",
        "duration_bucket_mismatch",
        "ready_for_n4_requires_tool_profile",
    }
)

HTTP_ERROR_CODES: frozenset[str] = N0N1_ERROR_CODES | N2_ERROR_CODES

# Issue / warn surface (not HTTP ErrorCode). Documented user-facing copy.
ISSUE_CODES: frozenset[str] = frozenset(
    {
        "tool_profile_unset",
        "named_cast_unreferenced",
        "named_cast_row_gap",
        "named_cast_auto_merged",
    }
)

# Documented user-facing HTTP codes that must appear in OpenAPI ErrorCode.
DOCUMENTED_USER_FACING_HTTP: frozenset[str] = frozenset(
    {
        "intent_unconfirmed",
        "intent_stale",
        "intent_lane_conflict",
        "named_cast_gate",
        "named_cast_missing",
        "duration_bucket_mismatch",
        "ready_for_n4_requires_tool_profile",
    }
)

# GAP-COPY machine / warn codes (banners). duration_below_camera_floor is details.reason.
GAP_COPY_CODES: frozenset[str] = frozenset(
    {
        "tool_profile_unset",
        "duration_bucket_mismatch",
        "ready_for_n4_requires_tool_profile",
    }
)

REQUIRED_018D_HTTP: frozenset[str] = DOCUMENTED_USER_FACING_HTTP

HTTP_STATUS: dict[str, int] = {
    "force_pass_forbidden": 400,
    "validation": 400,
    "not_found": 404,
    "conflict": 409,
    "locked": 409,
    "upstream_unlocked": 409,
    "downstream_locked": 409,
    "version_conflict": 409,
    "episode_abandoned": 409,
    "ready_for_n4_requires_tool_profile": 422,
}

# ----- duration machine tables (align 017b / CAM; no adsorb rewrite) ---------------

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
BUCKET_PROFILE_PREFIX = {
    "seedance_2": "seedance:",
    "kling": "kling:",
    "hailuo": "hailuo:",
    "veo": "veo:",
}
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

NAMED_CAST_BLOCKING = frozenset(
    {"named_cast_missing", "named_cast_unreferenced", "named_cast_row_gap"}
)

_MALE_IDENTITY_RE = re.compile(r"(男主|男主角|男性|男生|·男|／男|/男)")
_FEMALE_IDENTITY_RE = re.compile(r"(女主|女主角|女性|女生|·女|／女|/女)")

# ----- bilingual catalog (DESIGN-018d-COPY-BE §3 + existing n0n1) -------------------

MESSAGES: dict[str, dict[str, str]] = {
    "intent_unconfirmed": {
        "zh": "尚未确认入口意图。请先在意图确认页完成确认，再生成大纲。",
        "en": "Entry intent is not confirmed. Confirm intent before generating the outline.",
    },
    "intent_stale": {
        "zh": "入口意图已过期：关键设定（赛道/题材/身份或预挂）已变更，请重新确认后再生成。",
        "en": "Entry intent is stale: MUST fields changed. Re-confirm before generating.",
    },
    "intent_lane_conflict": {
        "zh": "赛道与预挂角色频向不一致。请使用「跟预挂改赛道」对齐后再确认。",
        "en": "Lane conflicts with preattached cast direction. Align lane (follow preattach) before confirming.",
    },
    "named_cast_gate": {
        "zh": "仍有具名角色未正确入表或未挂到分镜，无法通过门 G2。请处理角色表问题后再确认。",
        "en": "Named-cast issues remain; gate G2 cannot pass. Fix cast/storyboard linkage first.",
    },
    "named_cast_missing": {
        "zh": "对戏中的具名角色未出现在本集角色表中。请侧车补角或重新生成并入表。",
        "en": "A named speaking role is missing from the episode cast.",
    },
    "named_cast_unreferenced": {
        "zh": "角色表中有具名角色从未出现在任何分镜的人物列。请挂到镜头或移除。",
        "en": "A cast member is never referenced by any shot.",
    },
    "named_cast_row_gap": {
        "zh": "本镜出现了具名角色但人物列未包含对应 id。请补全 char_ids。",
        "en": "This shot mentions a named role not listed in char_ids.",
    },
    "named_cast_auto_merged": {
        "zh": "已自动将具名角色并入角色表（G1b 仍锁定，大纲正文未改）。",
        "en": "Named roles were auto-merged into cast (G1b still locked; outline unchanged).",
    },
    "tool_profile_unset": {
        "zh": "尚未选择出片工具。分镜门审仍可进行，但不能标记「可进下一出片节点」。请在需要出片前选择工具；系统会按工具允许的时长档校正各镜秒数。",
        "en": "No tool profile selected. Gate review may continue, but ready-for-n4 stays false until a tool is chosen.",
    },
    "duration_bucket_mismatch": {
        "zh": "还有镜的时长对不上当前工具档（例如写成了 2–3 秒，而当前工具只允许合法档）。请改秒数或重新吸附后再试。在全部对齐前，不能标记可出片。",
        "en": "One or more shot durations do not match the selected tool duration buckets. Fix or re-adsorb before ready-for-n4.",
    },
    "duration_below_camera_floor": {
        "zh": "「{camera}」这类镜头太短，可读性不够。请至少用到该工具的 {floor} 秒（或更高档）。",
        "en": 'Camera move "{camera}" is below the minimum readable duration for this tool ({floor}s).',
    },
    "ready_for_n4_requires_tool_profile": {
        "zh": "请先选择出片工具。未选工具时不能进入出片准备。",
        "en": "Select a tool profile before marking ready for n4.",
    },
    "force_pass_forbidden": {
        "zh": "禁止强制通过（ForcePass=never）。",
        "en": "ForcePass=never",
    },
    "lane_required": {
        "zh": "生成大纲前必须选择女频或男频赛道。",
        "en": "select female|male before generate",
    },
    "brief_incomplete": {
        "zh": "题材入口不完整：一句话题材与 PIN 不能都为空。",
        "en": "title_intent and pin both empty",
    },
    "locked": {
        "zh": "内容已锁定。如需改稿请先 unlock_edit。",
        "en": "locked; set unlock_edit to edit",
    },
    "upstream_unlocked": {
        "zh": "上游门 G1b 尚未锁定，不能读下游。",
        "en": "D-N1 not locked",
    },
    "downstream_locked": {
        "zh": "下游大纲已锁定；改 brief 须确认 stale。",
        "en": "outline locked; set confirm_stale_outline to write brief",
    },
    "version_conflict": {
        "zh": "版本冲突：If-Match 与当前 version 不一致。",
        "en": "If-Match mismatch",
    },
    "outline_empty": {
        "zh": "大纲缺少编号桥段，不能过门。",
        "en": "outline needs a numbered 桥段 sequence",
    },
    "outline_contains_prompts": {
        "zh": "大纲不得含提示词 / 宫格 / 出片参数。",
        "en": "outline must not contain prompts / 宫格 / Seedance / 出片 parameters",
    },
    "shot_cap_exceeded": {
        "zh": "镜头数超过硬上限。",
        "en": "shot_cap hard cap exceeded",
    },
    "cast_incomplete": {
        "zh": "角色表不完整：至少需要 1 个角色和 1 个场景。",
        "en": "need ≥1 character and ≥1 scene",
    },
    "episode_abandoned": {
        "zh": "本集已放弃，不能再写。",
        "en": "episode abandoned",
    },
    "not_found": {
        "zh": "资源不存在。",
        "en": "not found",
    },
    "conflict": {
        "zh": "资源冲突。",
        "en": "conflict",
    },
    "validation": {
        "zh": "请求校验失败。",
        "en": "validation",
    },
    "provider": {
        "zh": "生成服务不可用。请改用 fixture 或检查密钥。",
        "en": "LLM provider error",
    },
    "library_ref_unresolved": {
        "zh": "角色库引用无法解析（仅本项目库，D12）。",
        "en": "library_ref not in project library",
    },
}

CHIP_UNSET = "出片：未选工具"
CHIP_ALIGNED = "出片：时长已对齐 · {profile}"
CHIP_MISMATCH = "出片：时长未对齐"

UI_HINT_TOOL_UNSET = "未选工具：各镜可用任意意图秒数做分镜；选定工具后须落入该工具档位。"
UI_HINT_INTENT = "请先完成意图确认"
UI_HINT_NAMED_CAST_G2 = "具名配角 issue 未清时，G2 pass 将被阻断。"
UI_HINT_PROFILE_SWITCH = "更换出片工具后，将按新工具的允许秒数整表重算时长档。请确认后再出片。"


def lookup_messages(code: str, **fmt: Any) -> dict[str, str] | None:
    row = MESSAGES.get(code)
    if not row:
        return None
    zh, en = row["zh"], row["en"]
    if fmt:
        try:
            zh = zh.format(**fmt)
            en = en.format(**fmt)
        except (KeyError, IndexError, ValueError):
            pass
    return {"zh": zh, "en": en}


def user_message(code: str, fallback: str | None = None, **fmt: Any) -> str:
    found = lookup_messages(code, **fmt)
    if found:
        return found["zh"]
    return fallback or code


def raise_hard(code: str, *, status_code: int | None = None, **details: Any) -> None:
    """Raise AppError with catalog zh/en. Used by handlers (static CI collects this)."""
    reason = details.get("reason")
    fmt: dict[str, Any] = {}
    catalog_code = code
    if code == "duration_bucket_mismatch" and reason == "duration_below_camera_floor":
        catalog_code = "duration_below_camera_floor"
        fmt["camera"] = details.get("camera") or details.get("运镜") or "运镜"
        fmt["floor"] = details.get("floor") or details.get("下限") or details.get("duration_floor") or ""
    found = lookup_messages(catalog_code, **fmt) or lookup_messages(code)
    zh = (found or {}).get("zh") or code
    en = (found or {}).get("en") or zh
    status = status_code or HTTP_STATUS.get(code, 422)
    raise AppError(status, code, zh, messages={"zh": zh, "en": en}, **details)


def profile_selected(tool_profile: str | None) -> bool:
    return bool((tool_profile or "").strip())


def allowed_durations(tool_profile: str | None) -> list[int]:
    return sorted(TOOL_DURATION_ALLOWED.get(tool_profile or "", set()))


def camera_duration_floor(camera: str | None) -> int | None:
    if not camera:
        return None
    return CAMERA_DURATION_FLOOR.get(str(camera).strip())


def export_chip(tool_profile: str | None, *, aligned: bool | None) -> str:
    if not profile_selected(tool_profile):
        return CHIP_UNSET
    if aligned:
        return CHIP_ALIGNED.format(profile=tool_profile)
    return CHIP_MISMATCH


def infer_card_lane(card: dict[str, Any]) -> str | None:
    text = f"{card.get('name') or ''} {card.get('one_line') or ''}"
    male = bool(_MALE_IDENTITY_RE.search(text))
    female = bool(_FEMALE_IDENTITY_RE.search(text))
    if male and not female:
        return "male"
    if female and not male:
        return "female"
    return None


def lane_preattach_conflict(lane: str | None, cards: list[dict[str, Any]]) -> bool:
    if lane not in {"female", "male"} or not cards:
        return False
    return any(inferred and inferred != lane for card in cards if (inferred := infer_card_lane(card)))


def enforce_intent_for_generate(rec: dict[str, Any]) -> None:
    """018a-compatible hook. No ``intent`` key → no-op (main happy path)."""
    intent = rec.get("intent")
    if not isinstance(intent, dict):
        return
    if intent.get("confirmed") is not True:
        raise_hard("intent_unconfirmed", node="D-N0")
    if intent.get("stale") is True:
        raise_hard("intent_stale", node="D-N0")
    stored = intent.get("fingerprint")
    current = intent.get("current_fingerprint")
    if stored and current and stored != current:
        raise_hard("intent_stale", node="D-N0", stored=stored, current=current)


def enforce_intent_lane_for_confirm(lane: str | None, cards: list[dict[str, Any]]) -> None:
    if lane_preattach_conflict(lane, cards):
        raise_hard("intent_lane_conflict", lane=lane, node="D-N0")


def enforce_named_cast_gate(issues: list[dict[str, Any]], *, g2_pass: bool) -> None:
    blocking = [
        item
        for item in issues
        if str(item.get("code") or "").startswith("named_cast_")
        and item.get("code") != "named_cast_auto_merged"
    ]
    if g2_pass and blocking:
        raise_hard("named_cast_gate", issues=blocking, node="D-N2", gate="g2")


def enforce_named_cast_missing(issues: list[dict[str, Any]], *, mode: str) -> None:
    if mode != "error":
        return
    missing = [item for item in issues if item.get("code") == "named_cast_missing"]
    if missing:
        raise_hard("named_cast_missing", issues=missing, node="D-N2")


def collect_duration_issues(
    tool_profile: str | None,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not profile_selected(tool_profile):
        issues.append(
            {
                "severity": "warn",
                "code": "tool_profile_unset",
                "message": user_message("tool_profile_unset"),
                "messages": lookup_messages("tool_profile_unset"),
                "field": "tool_profile",
            }
        )
        return issues

    profile = str(tool_profile).strip()
    allow = set(allowed_durations(profile))
    prefix = BUCKET_PROFILE_PREFIX.get(profile)
    for row in rows:
        shot_id = row.get("shot_id")
        try:
            duration = int(row.get("duration_s"))
        except (TypeError, ValueError):
            duration = None
        camera = row.get("camera")
        bucket = row.get("tool_duration_bucket")
        common = {
            "shot_id": shot_id,
            "duration_s": duration,
            "tool_duration_bucket": bucket,
            "tool_profile": profile,
            "allowed_duration_s": sorted(allow),
        }
        if duration is None or duration not in allow:
            issues.append(
                {
                    "severity": "error",
                    "code": "duration_bucket_mismatch",
                    "reason": "duration_not_in_allow",
                    "message": user_message("duration_bucket_mismatch"),
                    "messages": lookup_messages("duration_bucket_mismatch"),
                    "field": "duration_s",
                    **common,
                }
            )
            continue
        floor = camera_duration_floor(camera if isinstance(camera, str) else None)
        if floor is not None and duration < floor:
            issues.append(
                {
                    "severity": "error",
                    "code": "duration_bucket_mismatch",
                    "reason": "duration_below_camera_floor",
                    "message": user_message(
                        "duration_below_camera_floor", camera=camera, floor=floor
                    ),
                    "messages": lookup_messages(
                        "duration_below_camera_floor", camera=camera, floor=floor
                    ),
                    "field": "duration_s",
                    "camera": camera,
                    "floor": floor,
                    **common,
                }
            )
        if bucket:
            if bucket not in TOOL_DURATION_BUCKETS:
                issues.append(
                    {
                        "severity": "error",
                        "code": "duration_bucket_mismatch",
                        "reason": "bucket_invalid",
                        "message": user_message("duration_bucket_mismatch"),
                        "messages": lookup_messages("duration_bucket_mismatch"),
                        "field": "tool_duration_bucket",
                        **common,
                    }
                )
            elif prefix and not str(bucket).startswith(prefix):
                issues.append(
                    {
                        "severity": "error",
                        "code": "duration_bucket_mismatch",
                        "reason": "bucket_family_mismatch",
                        "message": user_message("duration_bucket_mismatch"),
                        "messages": lookup_messages("duration_bucket_mismatch"),
                        "field": "tool_duration_bucket",
                        **common,
                    }
                )
            elif prefix and str(bucket) != f"{prefix}{duration}":
                issues.append(
                    {
                        "severity": "error",
                        "code": "duration_bucket_mismatch",
                        "reason": "bucket_seconds_mismatch",
                        "message": user_message("duration_bucket_mismatch"),
                        "messages": lookup_messages("duration_bucket_mismatch"),
                        "field": "tool_duration_bucket",
                        **common,
                    }
                )
    return issues


def _mismatch_details(hard: dict[str, Any]) -> dict[str, Any]:
    return {
        k: hard.get(k)
        for k in (
            "reason",
            "shot_id",
            "duration_s",
            "tool_duration_bucket",
            "tool_profile",
            "camera",
            "floor",
            "field",
            "allowed_duration_s",
        )
        if hard.get(k) is not None
    }


def enforce_duration_ready(
    tool_profile: str | None,
    rows: list[dict[str, Any]],
    *,
    ready_for_n4: bool,
) -> list[dict[str, Any]]:
    issues = collect_duration_issues(tool_profile, rows)
    if ready_for_n4 and not profile_selected(tool_profile):
        raise_hard("ready_for_n4_requires_tool_profile", field="tool_profile", node="D-N2")
    hard = next((i for i in issues if i.get("code") == "duration_bucket_mismatch"), None)
    if hard:
        raise_hard("duration_bucket_mismatch", **_mismatch_details(hard))
    return issues


def evaluate(raw: dict[str, Any], *, rec: dict[str, Any] | None = None) -> dict[str, Any]:
    """Thin handler used by POST .../drama/copy-contract/evaluate.

    Raises HTTP ErrorCodes when the snapshot is hard-blocked. Warn-only
    ``tool_profile_unset`` returns 200 + warnings (G2 still allowed).
    """
    incoming = raw if isinstance(raw, dict) else {}
    tool_profile = incoming.get("tool_profile")
    rows = incoming.get("rows") or []
    if not isinstance(rows, list):
        raise_hard("validation", status_code=422, field="rows")
    issues_in = incoming.get("named_cast_issues") or incoming.get("issues") or []
    if not isinstance(issues_in, list):
        issues_in = []
    g2_pass = bool(incoming.get("g2_pass"))
    want_ready = bool(incoming.get("ready_for_n4"))
    named_mode = str(incoming.get("named_cast_check") or "warn")
    warnings: list[dict[str, Any]] = []

    intent = incoming.get("intent")
    if isinstance(intent, dict):
        enforce_intent_for_generate({"intent": intent})
    if incoming.get("confirm_intent") is True:
        lane = incoming.get("lane")
        cards = incoming.get("preattached") or incoming.get("cards") or []
        if rec and not cards:
            cards = (rec.get("cast") or {}).get("characters") or []
            lane = lane or (rec.get("brief") or {}).get("lane_preference")
        if not isinstance(cards, list):
            cards = []
        enforce_intent_lane_for_confirm(lane, cards)

    enforce_named_cast_missing(issues_in, mode=named_mode)
    enforce_named_cast_gate(issues_in, g2_pass=g2_pass)

    duration_issues = enforce_duration_ready(tool_profile, rows, ready_for_n4=want_ready)
    for item in duration_issues:
        if item.get("code") == "tool_profile_unset":
            warnings.append(item)
    hard = next((i for i in duration_issues if i.get("code") == "duration_bucket_mismatch"), None)

    aligned = profile_selected(tool_profile) and hard is None
    return {
        "ok": True,
        "node": "D-N2",
        "copy_contract": "018d",
        "docs_pass": False,
        "warnings": warnings,
        "issues": duration_issues + list(issues_in),
        "chip": export_chip(tool_profile, aligned=aligned if profile_selected(tool_profile) else None),
        "ready_for_n4": False if not profile_selected(tool_profile) or hard else want_ready,
        "g2_pass_blocked": bool(
            [
                i
                for i in issues_in
                if str(i.get("code") or "").startswith("named_cast_")
                and i.get("code") != "named_cast_auto_merged"
            ]
        ),
        "hints": {
            "tool_profile_unset": UI_HINT_TOOL_UNSET,
            "intent": UI_HINT_INTENT,
            "named_cast_g2": UI_HINT_NAMED_CAST_G2,
            "profile_switch": UI_HINT_PROFILE_SWITCH,
        },
    }


def catalog_public() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "0.1.0",
        "docs_pass": False,
        "http_error_codes": {
            "n0n1": sorted(N0N1_ERROR_CODES),
            "n2": sorted(N2_ERROR_CODES),
        },
        "issue_codes": sorted(ISSUE_CODES),
        "messages": {code: dict(row) for code, row in sorted(MESSAGES.items())},
        "chips": {
            "unset": CHIP_UNSET,
            "aligned": CHIP_ALIGNED,
            "mismatch": CHIP_MISMATCH,
        },
    }
