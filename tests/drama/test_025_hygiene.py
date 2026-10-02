"""BRIEF-AIV-025 — Class-D SHOULD thicken + named_cast leak patch.

ForcePass=never. docs≠PASS. Does not claim product/G2/G3/LOOP-PASS.
Hard scan is CHAR name only. Class-D count/kinds warns must not alone block N4.
"""

from __future__ import annotations

from pathlib import Path

from aiv_drama.errors import AppError
from aiv_drama.models import SidecarAddCharacterRequest
from aiv_drama_n2.models import StoryboardGenerateRequest
from aiv_drama_n2.named_cast import (
    auto_merge_named_cast,
    classify_char_banlist,
    collect_named_hits,
    is_a_tier_prince_name,
    is_banlist_name,
    is_protected_lead,
    is_registerable_name,
    is_scene_b_class,
    is_spatial_scene_name,
    is_system_speaker,
    resolve_hit_names,
    resolve_to_pool_name,
)
from aiv_drama_n3.cards import materialize_cards
from aiv_drama_n2.skill_evidence import excerpt_borrowed_dongman
from aiv_drama_n2.validate import (
    CLASS_D_CAMERAS,
    CLASS_D_COUNT_BELOW_SUGGEST,
    CLASS_D_KINDS_BELOW_SUGGEST,
    CLASS_D_MONOCULTURE,
    CLASS_D_SUGGEST_CODES,
    class_d_shot_cameras,
    collect_class_d_suggest_issues,
    collect_issues,
    ready_for_n4,
)

from tests.drama.helpers import lock_g1b, sample_row, seed_project_episode

ALLOW_025 = (
    "程序员",
    "豆包",
    "GPT(CODEX)王子",
    "Opus5.5(CURSOR)王子",
    "GPT王子",
    "Opus5.5王子",
    "CODEX王子",
    "CURSOR(Opus5.5)王子",
)

DENY_025 = (
    ("正统王子", "B-TAG"),
    ("体验王子", "B-TAG"),
    ("重构王子", "B-TAG"),
    ("回滚王子", "B-TAG"),
    ("弹窗王子", "B-TAG"),
    ("破防王子", "B-TAG"),
    ("联猎王子", "B-TAG"),
    ("双屏王子", "B-TAG"),
    ("窗口王子", "B-TAG"),
    ("拆穿两位王子", "B-ACT"),
    ("吐槽程序员", "B-ACT"),
    ("吐槽程序员族", "B-ACT"),
    ("端水豆包", "B-ACT"),
    ("追杀程序员", "B-ACT"),
    ("屏幕里两位王子", "B-GEN"),
    ("弹幕里两位王子", "B-GEN"),
    ("双窗两位王子", "B-GEN"),
    ("IDE里两位王子", "B-GEN"),
    ("门外两位王子", "B-GEN"),
    ("幕外两位王子", "B-GEN"),
    ("王子", "B-GEN"),
    ("最优解", "B-TAG"),
    ("最贵解", "B-TAG"),
    ("联猎", "B-TAG"),
    ("非技术型AI", "B-TAG"),
    ("联猎非技术型AI", "B-TAG"),
    ("代码库已冻结", "B-FRAG"),
    ("倒计时开始", "B-FRAG"),
    ("清除非技术型AI", "B-FRAG"),
    ("吐槽两位王子", "B-ACT"),
    ("技术王子", "B-TAG"),
    ("幕里两位王子", "B-GEN"),
)

CAST_025 = {
    "characters": [
        {"id": "CHAR-01", "name": "程序员", "one_line": "男主"},
        {"id": "CHAR-02", "name": "豆包", "one_line": "破局"},
        {"id": "CHAR-03", "name": "GPT(CODEX)王子", "one_line": "CODEX王国技术王子"},
        {"id": "CHAR-04", "name": "Opus5.5(CURSOR)王子", "one_line": "CURSOR王国回滚王子"},
    ],
    "scenes": [{"id": "SCENE-01", "name": "侧边栏空间"}],
}


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def _row(i: int, camera: str, *, bridge: str = "B1", duration_s: int | None = None) -> dict:
    d_cam = camera in CLASS_D_CAMERAS
    duration = 8 if duration_s is None and d_cam else (5 if duration_s is None else duration_s)
    return sample_row(
        shot_id=f"S{i:02d}",
        seq=i,
        bridge_id=bridge,
        camera=camera,
        duration_s=duration,
        tool_duration_bucket=f"seedance:{duration}",
        char_ids=["CHAR-01"],
        scene_id="SCENE-01",
        action=f"镜{i:02d} {camera}",
    )


def _board(cameras: list[str], *, bridges: list[str] | None = None) -> list[dict]:
    rows = []
    for i, cam in enumerate(cameras, start=1):
        bridge = (bridges[i - 1] if bridges else f"B{((i - 1) // 4) + 1}")
        rows.append(_row(i, cam, bridge=bridge))
    return rows


def test_025_allow_guards_and_new_denies():
    for name in ALLOW_025:
        assert classify_char_banlist(name) == "ALLOW", name
        assert is_registerable_name(name), name
        assert not is_banlist_name(name), name
    assert is_protected_lead("程序员") and is_protected_lead("豆包")
    assert is_a_tier_prince_name("GPT(CODEX)王子")
    assert is_a_tier_prince_name("Opus5.5(CURSOR)王子")
    assert not is_a_tier_prince_name("回滚王子")
    assert not is_a_tier_prince_name("重构王子")
    for name, code in DENY_025:
        assert classify_char_banlist(name) == code, (name, classify_char_banlist(name))
        assert is_banlist_name(name), name
        assert not is_registerable_name(name), name


def test_025_name_slot_only_prose_does_not_kill_allow_rows():
    rec = {
        "outline": {
            "body_md": (
                "1. 开钩\n程序员与豆包\nCODEX王国技术王子与两位王子同时下达\n"
                "CURSOR王国回滚王子旁观\n"
            )
        },
        "cast": {
            "characters": [dict(row) for row in CAST_025["characters"]],
            "scenes": [dict(CAST_025["scenes"][0])],
            "version": 4,
            "locked": True,
        },
        "gate": {"locked": True, "last_decision": "pass"},
    }
    n = {"i": 4}

    def alloc(_rec):
        n["i"] += 1
        return f"CHAR-{n['i']:02d}"

    rows = [
        sample_row(
            shot_id="S01",
            seq=1,
            scene_id="SCENE-01",
            char_ids=["CHAR-01"],
            action="两位王子同时下达，技术王子只是职司描述",
            dialogue="程序员：最优解先放一边。",
        )
    ]
    hits = collect_named_hits(rows, cast=rec["cast"], outline_body=rec["outline"]["body_md"])
    registerable = {h["name"] for h in hits if h.get("registerable")}
    assert "技术王子" not in registerable
    assert "回滚王子" not in registerable
    assert "两位王子" not in registerable
    assert "最优解" not in registerable

    out_rows, _added = auto_merge_named_cast(rec, rows, alloc_char=alloc)
    names = [c["name"] for c in rec["cast"]["characters"]]
    assert "程序员" in names and "豆包" in names
    assert "GPT(CODEX)王子" in names
    assert "Opus5.5(CURSOR)王子" in names
    assert "技术王子" not in names
    assert "回滚王子" not in names
    assert "两位王子" not in names
    assert "最优解" not in names
    by_id = {c["id"]: c["name"] for c in rec["cast"]["characters"]}
    assert by_id["CHAR-03"] == "GPT(CODEX)王子"
    assert "技术王子" in by_id["CHAR-03"] or rec["cast"]["characters"][2]["one_line"] == "CODEX王国技术王子"
    assert rec["cast"]["characters"][3]["one_line"] == "CURSOR王国回滚王子"
    hung = {cid for r in out_rows for cid in r["char_ids"]}
    assert "CHAR-01" in hung


def test_025_bare_prince_folds_to_existing_a_tier():
    pool = ["GPT(CODEX)王子", "Opus5.5(CURSOR)王子", "程序员", "豆包"]
    assert resolve_to_pool_name("Opus王子", pool) in {"Opus5.5(CURSOR)王子", "Opus5.5王子"}
    folded = resolve_hit_names("王子", pool)
    assert "GPT(CODEX)王子" in folded
    assert "Opus5.5(CURSOR)王子" in folded
    assert "王子" not in folded
    assert classify_char_banlist("王子") == "B-GEN"
    assert not is_registerable_name("王子")


def test_025_sidecar_rejects_leaks_keeps_a_tier(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    for dirty in ("回滚王子", "最优解", "弹幕里两位王子", "代码库已冻结"):
        exc = _err(
            lambda name=dirty: svc.sidecar_add_character(
                pid, "EP01", SidecarAddCharacterRequest(name=name), raw={"name": name}
            )
        )
        assert exc.status_code == 422
        assert exc.code == "validation"
    env = svc.sidecar_add_character(
        pid,
        "EP01",
        SidecarAddCharacterRequest(name="Opus5.5(CURSOR)王子", one_line="CURSOR王国回滚王子"),
        raw={"name": "Opus5.5(CURSOR)王子"},
    )
    names = [c["name"] for c in env["cast"]["characters"]]
    assert "Opus5.5(CURSOR)王子" in names
    assert "回滚王子" not in names
    prince = next(c for c in env["cast"]["characters"] if c["name"] == "Opus5.5(CURSOR)王子")
    assert "回滚王子" in (prince.get("one_line") or "")


def test_class_d_closed_set_excludes_push_pull():
    assert "PUSH" not in CLASS_D_CAMERAS
    assert "PULL" not in CLASS_D_CAMERAS
    assert "CRANE_UP" not in CLASS_D_CAMERAS
    assert "STATIC_TO_MOVE" not in CLASS_D_CAMERAS
    rows = _board(["PUSH", "PULL", "CRANE_UP", "STATIC", "WHIP_PUSH", "HANDHELD"])
    assert class_d_shot_cameras(rows) == ["WHIP_PUSH", "HANDHELD"]


def test_class_d_suggest_warns_on_thin_12_shot_do_not_block_n4():
    # eng-023 shape: 3 Class-D / 3 kinds on a 12-shot board.
    cameras = [
        "STATIC",
        "PUSH",
        "STATIC",
        "WHIP_PUSH",
        "STATIC",
        "PULL",
        "PAN_H",
        "TRACK",
        "ORBIT",
        "STATIC",
        "HANDHELD",
        "STATIC",
    ]
    rows = _board(cameras)
    issues = collect_issues(
        rows,
        shot_cap=12,
        tool_profile="seedance_2",
        cast=CAST_025,
        outline_body="1. 开钩\n2. 立规\n3. 加压\n4. 主爽\n",
        named_cast_check="off",
    )
    codes = [i["code"] for i in issues]
    assert CLASS_D_COUNT_BELOW_SUGGEST in codes
    assert CLASS_D_KINDS_BELOW_SUGGEST in codes
    suggest = [i for i in issues if i["code"] in CLASS_D_SUGGEST_CODES]
    assert suggest and all(i["severity"] == "warn" for i in suggest)
    assert not any(i.get("severity") == "error" and i["code"] in CLASS_D_SUGGEST_CODES for i in issues)
    hard = [i for i in issues if i.get("severity") == "error"]
    assert not hard
    assert ready_for_n4("seedance_2", issues) is True


def test_class_d_monoculture_and_thick_board_clear():
    mono = _board(
        ["HANDHELD", "HANDHELD", "HANDHELD", "HANDHELD", "HANDHELD", "ORBIT"]
        + ["STATIC"] * 6
    )
    mono_issues = collect_class_d_suggest_issues(mono)
    mono_codes = {i["code"] for i in mono_issues}
    assert CLASS_D_MONOCULTURE in mono_codes
    assert CLASS_D_KINDS_BELOW_SUGGEST in mono_codes
    assert all(i["severity"] == "warn" for i in mono_issues)

    thick = _board(
        [
            "WHIP_PUSH",
            "STATIC",
            "WHIP_PULL",
            "DOLLY_ZOOM",
            "PUSH",
            "ROLL",
            "HANDHELD",
            "STATIC",
            "ORBIT",
            "STATIC",
            "PAN_H",
            "TRACK",
        ]
    )
    # 6 Class-D / 6 kinds, max 1 ≤ ceil(6/2)=3 → no suggest warns
    thick_issues = collect_class_d_suggest_issues(thick)
    assert thick_issues == []


def test_class_d_short_board_uses_lower_suggest():
    short = _board(["WHIP_PUSH", "ORBIT", "HANDHELD", "STATIC", "PUSH", "PULL"])
    assert len(short) <= 8
    issues = collect_class_d_suggest_issues(short)
    assert issues == []  # 3 count / 3 kinds meets short-board SHOULD
    thinner = _board(["WHIP_PUSH", "WHIP_PUSH", "STATIC", "PUSH", "PULL", "PAN_H"])
    thin_codes = {i["code"] for i in collect_class_d_suggest_issues(thinner)}
    assert CLASS_D_COUNT_BELOW_SUGGEST in thin_codes
    assert CLASS_D_KINDS_BELOW_SUGGEST in thin_codes
    assert CLASS_D_MONOCULTURE in thin_codes


def test_class_d_duration_floor_still_hard_with_profile():
    rows = [_row(1, "DOLLY_ZOOM", duration_s=5)]
    rows[0]["tool_duration_bucket"] = "seedance:5"
    hard = collect_issues(
        rows,
        shot_cap=12,
        tool_profile="seedance_2",
        cast=CAST_025,
        outline_body="1. 开钩\n",
        named_cast_check="off",
    )
    floor = [i for i in hard if i["code"] == "duration_below_camera_floor"]
    assert floor and floor[0]["severity"] == "error"
    assert ready_for_n4("seedance_2", hard) is False
    soft = collect_issues(
        rows,
        shot_cap=12,
        tool_profile=None,
        cast=CAST_025,
        outline_body="1. 开钩\n",
        named_cast_check="off",
    )
    floor_soft = [i for i in soft if i["code"] == "duration_below_camera_floor"]
    assert floor_soft and floor_soft[0]["severity"] == "warn"


def test_storyboard_skill_excerpt_has_class_d_guidance(svc):
    excerpt, paths, _meta = excerpt_borrowed_dongman(svc.settings)
    assert any("动态漫-转分镜" in p for p in paths)
    assert "WHIP_PUSH" in excerpt
    assert "DOLLY_ZOOM" in excerpt
    assert "HANDHELD" in excerpt
    assert "8" in excerpt and "10" in excerpt
    skill = Path(svc.settings.repo_root) / ".skill" / "writing" / "动态漫-转分镜" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "WHIP_PULL" in text
    assert "禁止 5" in text or "禁 5" in text
    llm = Path(svc.settings.repo_root) / "packages" / "drama-n2-core" / "aiv_drama_n2" / "provider" / "llm.py"
    rules = llm.read_text(encoding="utf-8")
    assert "ceil(D_count/2)" in rules or "ceil" in rules
    assert "回滚王子" in rules
    assert "NAME slot only" in rules


def test_025_force_pass_still_forbidden(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    exc = _err(
        lambda: svc.confirm_gate_g2(
            pid, "EP01", {"decision": "pass", "actor": "yangzhou", "force_pass": True}
        )
    )
    assert exc.status_code == 400
    assert exc.code == "force_pass_forbidden"
    exc2 = _err(
        lambda: svc.validate_storyboard(pid, "EP01", raw={"force_pass": True})
    )
    assert exc2.status_code == 400
    assert exc2.code == "force_pass_forbidden"


def test_025_validate_suggest_on_generated_fixture_is_warn_only(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    svc.generate_storyboard(
        pid,
        "EP01",
        StoryboardGenerateRequest(provider="fixture", tool_profile="seedance_2"),
        raw={"provider": "fixture", "tool_profile": "seedance_2"},
    )
    val = svc.validate_storyboard(pid, "EP01")
    suggest = [i for i in val["issues"] if i["code"] in CLASS_D_SUGGEST_CODES]
    assert suggest
    assert all(i["severity"] == "warn" for i in suggest)
    assert val["valid"] is True
    assert not any(i.get("severity") == "error" and i["code"] in CLASS_D_SUGGEST_CODES for i in val["issues"])


def test_025_scene_popup_space_allow_char_popup_prince_deny():
    """eng-025 live: SCENE 弹窗空间 must materialize; CHAR 弹窗王子 stays DENY."""
    assert is_spatial_scene_name("弹窗空间")
    assert not is_scene_b_class("弹窗空间")
    # CHAR path still sees the 弹窗 prefix; SCENE bucket must not inherit that skip.
    assert is_system_speaker("弹窗空间")
    assert is_system_speaker("弹窗")
    assert is_scene_b_class("弹窗")
    assert is_scene_b_class("系统音")
    assert classify_char_banlist("弹窗王子") == "B-TAG"
    assert is_banlist_name("弹窗王子")
    assert not is_registerable_name("弹窗王子")
    assert classify_char_banlist("弹窗") != "ALLOW"
    assert is_banlist_name("系统音") or is_system_speaker("系统音")
    for name in (
        "侧边栏空间",
        "避难所门厅",
        "深夜IDE战场",
        "侧边栏奶茶时刻",
        "开源避难所入口",
    ):
        assert is_spatial_scene_name(name) or not is_scene_b_class(name), name
        assert not is_scene_b_class(name), name

    cast = {
        "characters": [
            {"id": "CHAR-01", "name": "程序员", "one_line": "男主"},
            {"id": "CHAR-05", "name": "弹窗王子", "one_line": "脏TAG"},
            {"id": "CHAR-06", "name": "系统音", "one_line": "VO"},
            {"id": "CHAR-07", "name": "弹窗", "one_line": "裸系统"},
        ],
        "scenes": [
            {"id": "SCENE-01", "name": "侧边栏空间", "one_line": "陪伴"},
            {"id": "SCENE-02", "name": "避难所门厅", "one_line": "门厅"},
            {"id": "SCENE-03", "name": "弹窗空间", "one_line": "双窗对撞"},
            {"id": "SCENE-04", "name": "深夜IDE战场", "one_line": "战场"},
            {"id": "SCENE-05", "name": "系统音", "one_line": "误用系统名"},
        ],
    }
    storyboard = {
        "rows": [
            {"shot_id": "S03", "char_ids": ["CHAR-01"], "scene_id": "SCENE-03"},
            {"shot_id": "S07", "char_ids": ["CHAR-01"], "scene_id": "SCENE-03"},
        ]
    }
    characters, scenes, skipped = materialize_cards(cast, storyboard)
    char_ids = {c["id"] for c in characters}
    scene_ids = {s["id"] for s in scenes}
    scene_names = {s["name"] for s in scenes}
    assert "CHAR-01" in char_ids
    assert "CHAR-05" not in char_ids
    assert "CHAR-06" not in char_ids
    assert "CHAR-07" not in char_ids
    assert "SCENE-03" in scene_ids
    assert "弹窗空间" in scene_names
    assert {"SCENE-01", "SCENE-02", "SCENE-04"} <= scene_ids
    assert "SCENE-05" not in scene_ids
    skipped_ids = {str(w.get("id") or "") for w in skipped if w.get("code") == "b_class_skipped"}
    assert "SCENE-03" not in skipped_ids
    assert {"CHAR-05", "CHAR-06", "CHAR-07", "SCENE-05"} <= skipped_ids


def test_029_scene_popup_courtroom_materializes_chrome_still_skips():
    """DIR EVAL: 弹窗审判庭 is a space noun; do not skip SCENE-03 (S05/S06 hang)."""
    assert is_spatial_scene_name("弹窗审判庭")
    assert not is_scene_b_class("弹窗审判庭")
    # CHAR/N2 chrome detector may still see the 弹窗 prefix; SCENE bucket must not inherit skip.
    assert is_system_speaker("弹窗审判庭")
    assert is_system_speaker("弹窗")
    assert is_system_speaker("系统音")
    assert is_scene_b_class("弹窗")
    assert is_scene_b_class("弹窗字")
    assert is_scene_b_class("系统音")
    assert classify_char_banlist("弹窗王子") == "B-TAG"
    assert is_banlist_name("弹窗王子")
    assert is_scene_b_class("弹窗王子")

    cast = {
        "characters": [
            {"id": "CHAR-01", "name": "程序员", "one_line": "男主"},
            {"id": "CHAR-05", "name": "弹窗王子", "one_line": "脏TAG"},
            {"id": "CHAR-06", "name": "系统音", "one_line": "VO"},
        ],
        "scenes": [
            {"id": "SCENE-03", "name": "弹窗审判庭", "one_line": "对质空间"},
            {"id": "SCENE-05", "name": "弹窗", "one_line": "裸系统"},
            {"id": "SCENE-06", "name": "系统音", "one_line": "误用系统名"},
        ],
    }
    storyboard = {
        "rows": [
            {"shot_id": "S05", "char_ids": ["CHAR-01"], "scene_id": "SCENE-03"},
            {"shot_id": "S06", "char_ids": ["CHAR-01"], "scene_id": "SCENE-03"},
        ]
    }
    characters, scenes, skipped = materialize_cards(cast, storyboard)
    char_ids = {c["id"] for c in characters}
    scene_ids = {s["id"] for s in scenes}
    scene_names = {s["name"] for s in scenes}
    assert "CHAR-01" in char_ids
    assert "CHAR-05" not in char_ids
    assert "CHAR-06" not in char_ids
    assert "SCENE-03" in scene_ids
    assert "弹窗审判庭" in scene_names
    assert "SCENE-05" not in scene_ids
    assert "SCENE-06" not in scene_ids
    skipped_ids = {str(w.get("id") or "") for w in skipped if w.get("code") == "b_class_skipped"}
    assert "SCENE-03" not in skipped_ids
    assert {"CHAR-05", "CHAR-06", "SCENE-05", "SCENE-06"} <= skipped_ids
    # Do not "fix green" by rewriting shot scene_ids.
    assert [row["scene_id"] for row in storyboard["rows"]] == ["SCENE-03", "SCENE-03"]
