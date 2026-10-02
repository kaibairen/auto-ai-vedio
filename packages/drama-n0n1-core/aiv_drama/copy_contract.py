"""018d COPY-CONTRACT catalog + thin evaluate overlay.

SoT for bilingual ErrorCode / GAP-COPY banners. Evaluate uses the live N2
duration tables (no adsorb rewrite, no N0–N2 LLM body change).
ForcePass=never; docs≠PASS.
"""

from __future__ import annotations

from typing import Any

from aiv_drama.errors import AppError
from aiv_drama_n2.named_cast import INFORMATIONAL_NAMED_CAST, NAMED_CAST_PREFIX

# ----- HTTP ErrorCode (must match OpenAPI enums) -----------------------------------

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
        "validation",
        "not_found",
        "conflict",
        "locked",
        "upstream_unlocked",
        "stale_upstream",
        "version_conflict",
        "shot_cap_exceeded",
        "storyboard_empty",
        "storyboard_incomplete",
        "prompt_forbidden",
        "cast_id_unknown",
        "bridge_id_missing",
        "shot_id_duplicate",
        "seq_invalid",
        "cam_enum_invalid",
        "duration_bucket_mismatch",
        "duration_below_camera_floor",
        "episode_abandoned",
        "force_pass_forbidden",
        "provider",
        "projection_dirty",
        "wrong_profile",
        "named_cast_gate",
        "named_cast_missing",
        "ready_for_n4_requires_tool_profile",
    }
)

HTTP_ERROR_CODES: frozenset[str] = N0N1_ERROR_CODES | N2_ERROR_CODES

# Documented issue / warn surface (not HTTP ErrorCode).
ISSUE_CODES: frozenset[str] = frozenset(
    {
        "tool_profile_unset",
        "named_cast_unreferenced",
        "named_cast_row_gap",
        "named_cast_auto_merged",
        "duration_below_camera_floor",
        "class_d_count_below_suggest",
        "class_d_kinds_below_suggest",
        "class_d_monoculture",
    }
)

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

GAP_COPY_CODES: frozenset[str] = frozenset(
    {
        "tool_profile_unset",
        "duration_bucket_mismatch",
        "ready_for_n4_requires_tool_profile",
    }
)

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
    "usable_for_n4_false": 409,
    "not_ready_for_n4": 409,
    "missing_card": 422,
    "validation_failed": 422,
    "duration_out_of_profile": 422,
    "prompt_too_long": 422,
}

CHIP_UNSET = "出片：未选工具"
CHIP_ALIGNED = "出片：时长已对齐 · {profile}"
CHIP_MISMATCH = "出片：时长未对齐"

UI_HINT_TOOL_UNSET = "未选工具：各镜可用任意意图秒数做分镜；选定工具后须落入该工具档位。"
UI_HINT_INTENT = "请先完成意图确认"
UI_HINT_NAMED_CAST_G2 = "具名配角 issue 未清时，G2 pass 将被阻断。"
UI_HINT_PROFILE_SWITCH = "更换出片工具后，将按新工具的允许秒数整表重算时长档。请确认后再出片。"

MESSAGES: dict[str, dict[str, str]] = {
    "intent_unconfirmed": {
        "zh": "请先完成意图确认，再生成大纲。",
        "en": "Entry intent is not confirmed. Confirm intent before generating the outline.",
    },
    "intent_stale": {
        "zh": "意图字段已变更，请重新确认后再生成大纲。",
        "en": "Entry intent is stale: MUST fields changed. Re-confirm before generating.",
    },
    "intent_lane_conflict": {
        "zh": "赛道与预挂频向冲突，请先一键跟预挂改 lane。",
        "en": "Lane conflicts with preattached cast direction. Align lane before confirming.",
    },
    "named_cast_gate": {
        "zh": "还有未入表的具名角色，无法通过分镜门审。",
        "en": "Named-cast issues remain; gate G2 cannot pass.",
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
        "zh": "类 D 运镜（手持/急推急拉/环绕/滑动变焦/旋转）时长须 ≥8 秒。请升到 8 或 10，勿停留在 5 秒档。",
        "en": "Class-D camera moves (HANDHELD/WHIP_*/ORBIT/DOLLY_ZOOM/ROLL) require duration_s ≥ 8.",
    },
    "class_d_count_below_suggest": {
        "zh": "约 12 镜板上 Class-D 条数低于建议（目标 ≥5；短板 ≥3）。此为软建议，不单独挡分镜门审或出片就绪。",
        "en": "Class-D shot count is below the SHOULD suggest. Warning only; does not alone block G2 or ready_for_n4.",
    },
    "class_d_kinds_below_suggest": {
        "zh": "Class-D 相异枚举种类低于建议（目标 ≥4；短板 ≥3）。请轮换晃镜，勿只堆一种。软建议，不单独挡门。",
        "en": "Class-D distinct kinds are below the SHOULD suggest. Rotate WHIP_*/DOLLY_ZOOM/ROLL/HANDHELD/ORBIT. Warning only.",
    },
    "class_d_monoculture": {
        "zh": "单一 Class-D 枚举超过 ⌈条数/2⌉ 建议上限。勿用同一种晃镜填满条数。软建议，不单独挡门。",
        "en": "One Class-D kind exceeds the ⌈count/2⌉ SHOULD cap. Warning only; does not alone block ready_for_n4.",
    },
    "ready_for_n4_requires_tool_profile": {
        "zh": "请先选择出片工具。未选工具时不能进入出片准备。",
        "en": "Select a tool profile before marking ready for n4.",
    },
    "force_pass_forbidden": {
        "zh": "禁止强制通过（ForcePass=never）。",
        "en": "ForcePass=never",
    },
    "usable_for_n4_false": {
        "zh": "usable_for_n4=false · 缺图/缺 ref，拒绝写盘。",
        "en": "usable_for_n4 is false; missing refs/images — jsonl not written.",
    },
    "bare_id_in_prompt": {
        "zh": "prompt 禁止只留裸 CHAR-/SCENE- ID，须替换为中文特征。",
        "en": "Prompt must not keep bare CHAR-/SCENE- ids; replace with Chinese features.",
    },
    "empty_negative": {
        "zh": "negative 不可为空（NEG_CORE）。",
        "en": "negative must be non-empty (NEG_CORE).",
    },
    "unsupported_tool_profile": {
        "zh": "本拍工具闭集只落盘 seedance_2（入参别名 seedance_2_0 可接受）。",
        "en": "This shot persists only seedance_2 (seedance_2_0 is an input alias).",
    },
    "not_ready_for_n4": {
        "zh": "ready_for_n4=false · 未选 tool_profile 或分镜硬检未过，拒绝写盘。",
        "en": "ready_for_n4 is false; select a tool profile and pass N2 hard checks before assemble.",
    },
    "missing_card": {
        "zh": "镜绑定 CHAR/SCENE 无卡，拒绝写盘。",
        "en": "A bound CHAR/SCENE id has no card; jsonl not written.",
    },
    "validation_failed": {
        "zh": "N4 硬规则校验失败，拒绝写盘。",
        "en": "N4 hard validation failed; jsonl not written.",
    },
    "duration_out_of_profile": {
        "zh": "duration_s 须落入 seedance_2 档 {5,8,10}。",
        "en": "duration_s must be in seedance_2 set {5,8,10}.",
    },
    "prompt_too_long": {
        "zh": "prompt 超过 adapter 上限。",
        "en": "prompt exceeds the adapter max_prompt_len.",
    },
    "lane_required": {
        "zh": "生成大纲前必须选择女频或男频赛道。",
        "en": "select female|male before generate",
    },
    "validation": {
        "zh": "请求校验失败。",
        "en": "validation",
    },
    "material_bind": {
        "zh": "材料绑定门未过（脸 ref path+md5）；禁 generate。",
        "en": "Material bind gate failed (face ref path+md5); generate blocked.",
    },
    "look_card_incomplete": {
        "zh": "厚卡缺 wardrobe/appearance 与 immutable；禁助手自写合板服装正文。",
        "en": "Thick card missing wardrobe/appearance and immutable; do not invent sheet clothing.",
    },
    "scene_look_forbidden": {
        "zh": "金样 A 合板仅 CHAR；SCENE 另轨。",
        "en": "Gold-A sheet is CHAR-only; SCENE is a separate track.",
    },
    "g4_required": {
        "zh": "门 G4 未锁定（或书面子集未过审），禁止 N5b submit。",
        "en": "Gate G4 is not locked (or written subset not approved); N5b submit blocked.",
    },
    "live_job_forbidden": {
        "zh": "N5b skeleton：默认禁真 Job POST（未设 AIV_N5B_ALLOW_LIVE_JOB）。",
        "en": "N5b skeleton forbids live Job POST unless AIV_N5B_ALLOW_LIVE_JOB is set.",
    },
    "n5b_impl_hold": {
        "zh": "N5b IMPL HOLD：即便允许 live 标志，本骨架仍不 POST create task。",
        "en": "N5b IMPL is HOLD; skeleton never POSTs create even if the live flag is set.",
    },
    "clips_required": {
        "zh": "门 G5 pass 需要 clips/<shot_id>.mp4 + .meta.json（SKU/job_id/md5），且 md5 与字节一致。",
        "en": "G5 pass needs clips/<shot_id>.mp4 + .meta.json (SKU/job_id/md5) with matching md5.",
    },
    "fake_pixels_forbidden": {
        "zh": "禁假像素/彩条/静帧循环冒充 clips。",
        "en": "Fake pixels / colorbars / still loops are forbidden as clips.",
    },
    "prompts_required": {
        "zh": "缺 EP##-prompts.jsonl；N5b 只映射已拼装行，不发明镜头。",
        "en": "EP##-prompts.jsonl is missing; N5b maps assembled lines only.",
    },
}


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
    """Raise AppError with catalog zh/en. Static CI collects these string literals."""
    found = lookup_messages(code)
    zh = (found or {}).get("zh") or code
    en = (found or {}).get("en") or zh
    status = status_code or HTTP_STATUS.get(code, 422)
    raise AppError(status, code, zh, messages={"zh": zh, "en": en}, **details)


def profile_selected(tool_profile: str | None) -> bool:
    return bool((tool_profile or "").strip())


def export_chip(tool_profile: str | None, *, aligned: bool | None) -> str:
    if not profile_selected(tool_profile):
        return CHIP_UNSET
    if aligned:
        return CHIP_ALIGNED.format(profile=tool_profile)
    return CHIP_MISMATCH


def decorate_issue(item: dict[str, Any]) -> dict[str, Any]:
    out = dict(item)
    code = str(out.get("code") or "")
    found = lookup_messages(code)
    if found:
        out["message"] = found["zh"]
        out["messages"] = found
    return out


def collect_duration_issues(
    tool_profile: str | None,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reuse live N2 collect_issues; keep only GAP-COPY duration/profile codes."""
    from aiv_drama_n2.validate import collect_issues

    padded: list[dict[str, Any]] = []
    for index, row in enumerate(rows or [], start=1):
        if not isinstance(row, dict):
            continue
        char_ids = row.get("char_ids")
        padded.append(
            {
                "shot_id": row.get("shot_id") or f"S{index:02d}",
                "bridge_id": row.get("bridge_id") or "B1",
                "seq": row.get("seq") or index,
                "duration_s": row.get("duration_s") if row.get("duration_s") is not None else 0,
                "shot_size": row.get("shot_size") or "MS",
                "camera": row.get("camera") or "STATIC",
                "action": row.get("action") or "copy-contract",
                "char_ids": char_ids if isinstance(char_ids, list) else ["NONE"],
                "scene_id": row.get("scene_id") or "NONE",
                "tool_duration_bucket": row.get("tool_duration_bucket"),
                "notes": row.get("notes") or "copy-contract snapshot",
            }
        )
    issues = collect_issues(
        padded,
        shot_cap=12,
        tool_profile=tool_profile if profile_selected(tool_profile) else None,
        cast=None,
        named_cast_check="off",
    )
    keep = {"tool_profile_unset", "duration_bucket_mismatch", "duration_below_camera_floor"}
    return [decorate_issue(item) for item in issues if item.get("code") in keep]


def _blocking_named(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in issues:
        code = str(item.get("code") or "")
        if code.startswith(NAMED_CAST_PREFIX) and code not in INFORMATIONAL_NAMED_CAST:
            out.append(item)
    return out


def _mismatch_details(hard: dict[str, Any]) -> dict[str, Any]:
    details = dict(hard.get("details") or {})
    for key in ("shot_id", "field", "duration_s", "tool_duration_bucket", "tool_profile"):
        if hard.get(key) is not None:
            details.setdefault(key, hard.get(key))
        inner = hard.get("details") or {}
        if isinstance(inner, dict) and inner.get(key) is not None:
            details.setdefault(key, inner.get(key))
    return details


def evaluate(raw: dict[str, Any], *, rec: dict[str, Any] | None = None) -> dict[str, Any]:
    """Thin POST .../drama/copy-contract/evaluate overlay.

    Snapshot rows are optional; stored storyboard rows are used when omitted.
    Does not rewrite generate / adsorb / G2 runtime.
    """
    incoming = raw if isinstance(raw, dict) else {}
    tool_profile = incoming.get("tool_profile")
    rows = incoming.get("rows")
    if rows is None and rec:
        rows = ((rec.get("storyboard") or {}).get("rows")) or []
        if tool_profile is None:
            tool_profile = (rec.get("storyboard") or {}).get("tool_profile")
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise_hard("validation", status_code=422, field="rows")
    issues_in = incoming.get("named_cast_issues") or incoming.get("issues") or []
    if not isinstance(issues_in, list):
        issues_in = []
    g2_pass = bool(incoming.get("g2_pass"))
    want_ready = bool(incoming.get("ready_for_n4"))
    named_mode = str(incoming.get("named_cast_check") or "warn")

    if want_ready and not profile_selected(tool_profile):
        raise_hard("ready_for_n4_requires_tool_profile", field="tool_profile", node="D-N2")

    missing = [item for item in issues_in if item.get("code") == "named_cast_missing"]
    if named_mode == "error" and missing:
        raise_hard("named_cast_missing", issues=missing, node="D-N2")

    blocking = _blocking_named(issues_in)
    if g2_pass and blocking:
        raise_hard("named_cast_gate", issues=blocking, node="D-N2", gate="g2")

    duration_issues = collect_duration_issues(tool_profile, rows)
    hard = next((item for item in duration_issues if item.get("code") == "duration_bucket_mismatch"), None)
    if hard:
        raise_hard("duration_bucket_mismatch", **_mismatch_details(hard))

    warnings = [item for item in duration_issues if item.get("code") == "tool_profile_unset"]
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
        "g2_pass_blocked": bool(blocking),
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
