"""BRIEF-AIV-023 — named_cast Acc#3 banlist, SCENE bucket, Class-D ≥8.

ForcePass=never. docs≠PASS. Does not claim product/G2/G3/LOOP-PASS.
"""

from __future__ import annotations

from aiv_drama.errors import AppError
from aiv_drama.models import GeneratedDraft, OutlineGenerateRequest, SidecarAddCharacterRequest
from aiv_drama.provider.fixture import FixtureProvider
from aiv_drama_n2.duration import adsorb_duration, adsorb_row
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
    prefer_spatial_scene_name,
)
from aiv_drama_n2.validate import collect_issues
from aiv_drama_n3.cards import materialize_cards
from aiv_drama_n3.models import N3MaterializeRequest

from tests.drama.helpers import lock_g1b, persist_and_confirm_intent, sample_row, seed_project_episode


DENY_NAMES = (
    "吐槽两位王子",
    "技术王子",
    "幕里两位王子",
    "两位王子",
    "两侧王子",
    "幕里的王子",
    "屏幕里两位王子",
    "CURSOR",
    "CODEX",
)
ALLOW_NAMES = (
    "程序员",
    "豆包",
    "GPT(CODEX)王子",
    "Opus5.5(CURSOR)王子",
    "GPT王子",
    "Opus5.5王子",
    "CODEX王子",
    "CURSOR(Opus5.5)王子",
)


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def test_banlist_allow_deny_table():
    assert classify_char_banlist("吐槽两位王子") == "B-ACT"
    assert classify_char_banlist("技术王子") == "B-TAG"
    assert classify_char_banlist("幕里两位王子") == "B-GEN"
    assert classify_char_banlist("两位王子") == "B-GEN"
    assert classify_char_banlist("两侧王子") == "B-GEN"
    assert classify_char_banlist("幕里的王子") == "B-GEN"
    assert classify_char_banlist("CURSOR") == "B-BARE"
    assert classify_char_banlist("CODEX") == "B-BARE"
    for name in DENY_NAMES:
        assert is_banlist_name(name), name
        assert not is_registerable_name(name), name
    for name in ALLOW_NAMES:
        assert classify_char_banlist(name) == "ALLOW", name
        assert is_registerable_name(name), name
        assert not is_banlist_name(name), name
    assert is_protected_lead("程序员") and is_protected_lead("豆包")
    assert is_a_tier_prince_name("GPT(CODEX)王子")
    assert is_a_tier_prince_name("Opus5.5(CURSOR)王子")
    assert not is_a_tier_prince_name("技术王子")
    assert not is_a_tier_prince_name("吐槽CODEX王子")


def test_scene_bucket_does_not_reuse_char_punches():
    for name in (
        "侧边栏奶茶时刻",
        "开源避难所入口",
        "侧边栏空间",
        "避难所门厅",
        "深夜IDE战场",
        "开源避难所",
        "IDE侧栏",
        "弹窗空间",
        "弹窗审判庭",
    ):
        assert not is_scene_b_class(name), name
    for name in ("吐槽两位王子", "指出两王子", "两位王子", "系统音", "弹窗", "弹窗字"):
        assert is_scene_b_class(name), name
    assert prefer_spatial_scene_name("侧边栏奶茶时刻") == "侧边栏空间"
    assert prefer_spatial_scene_name("开源避难所入口") == "避难所门厅"
    assert prefer_spatial_scene_name("深夜IDE战场") == "深夜IDE战场"


def _eng021_dirty_rows(scene: str, lead: str) -> list[dict]:
    return [
        sample_row(
            shot_id="S09",
            seq=9,
            scene_id=scene,
            char_ids=[lead],
            action="吐槽两位王子与技术王子、幕里两位王子同框",
            dialogue="吐槽两位王子：两位王子退兵。技术王子：覆盖。幕里两位王子：回滚。",
        ),
        sample_row(
            shot_id="S01",
            seq=1,
            scene_id=scene,
            char_ids=[lead],
            action="GPT(CODEX)王子与Opus5.5(CURSOR)王子弹窗夹击",
            dialogue="GPT(CODEX)王子：联猎。",
        ),
    ]


def test_auto_merge_rejects_021_dirty_keeps_leads_and_princes():
    rec = {
        "outline": {
            "body_md": (
                "1. 开钩\n程序员与豆包\nGPT(CODEX)王子 / Opus5.5(CURSOR)王子\n"
                "吐槽两位王子 技术王子 幕里两位王子\n"
            )
        },
        "cast": {
            "characters": [
                {"id": "CHAR-01", "name": "程序员"},
                {"id": "CHAR-02", "name": "豆包"},
                {"id": "CHAR-05", "name": "吐槽两位王子"},
                {"id": "CHAR-06", "name": "技术王子"},
                {"id": "CHAR-07", "name": "幕里两位王子"},
            ],
            "scenes": [{"id": "SCENE-01", "name": "侧边栏奶茶时刻"}],
            "version": 3,
            "locked": True,
        },
        "gate": {"locked": True, "last_decision": "pass"},
    }
    n = {"i": 7}

    def alloc(_rec):
        n["i"] += 1
        return f"CHAR-{n['i']:02d}"

    hits = collect_named_hits(
        _eng021_dirty_rows("SCENE-01", "CHAR-01"),
        cast=rec["cast"],
        outline_body=rec["outline"]["body_md"],
    )
    registerable = {h["name"] for h in hits if h.get("registerable")}
    assert "吐槽两位王子" not in registerable
    assert "技术王子" not in registerable
    assert "幕里两位王子" not in registerable

    rows, _added = auto_merge_named_cast(
        rec, _eng021_dirty_rows("SCENE-01", "CHAR-01"), alloc_char=alloc
    )
    names = [c["name"] for c in rec["cast"]["characters"]]
    assert "程序员" in names and "豆包" in names
    assert "吐槽两位王子" not in names
    assert "技术王子" not in names
    assert "幕里两位王子" not in names
    assert "两位王子" not in names
    assert "CURSOR" not in names and "CODEX" not in names
    assert "GPT(CODEX)王子" in names or "GPT王子" in names or "CODEX王子" in names
    assert (
        "Opus5.5(CURSOR)王子" in names
        or "Opus5.5王子" in names
        or "CURSOR(Opus5.5)王子" in names
    )
    by_name = {c["name"]: c["id"] for c in rec["cast"]["characters"]}
    hung = {cid for r in rows for cid in r["char_ids"]}
    assert by_name["程序员"] in hung
    assert by_name["豆包"] in {c["id"] for c in rec["cast"]["characters"]}
    dirty_ids = {"CHAR-05", "CHAR-06", "CHAR-07"}
    assert dirty_ids.isdisjoint(hung)


def test_generate_skips_021_dirty_names(svc, monkeypatch):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    rec["outline"]["body_md"] = (
        rec["outline"]["body_md"]
        + "\n程序员 豆包 GPT(CODEX)王子 Opus5.5(CURSOR)王子\n吐槽两位王子 技术王子 幕里两位王子\n"
    )
    rec["cast"]["characters"][0]["name"] = "程序员"
    rec["cast"]["characters"][1]["name"] = "豆包"
    lead = rec["cast"]["characters"][0]["id"]
    scene = rec["cast"]["scenes"][0]["id"]

    def fake_rows(settings, **kw):
        return _eng021_dirty_rows(scene, lead)

    monkeypatch.setattr("aiv_drama_n2.ops.generate_rows", fake_rows)
    env = svc.generate_storyboard(
        pid, "EP01", StoryboardGenerateRequest(provider="llm"), raw={"provider": "llm"}
    )
    rec = svc._rec(pid, "EP01")
    names = [c["name"] for c in rec["cast"]["characters"]]
    assert "程序员" in names and "豆包" in names
    assert "吐槽两位王子" not in names
    assert "技术王子" not in names
    assert "幕里两位王子" not in names
    assert "CURSOR" not in names and "CODEX" not in names
    assert any(is_a_tier_prince_name(n) for n in names)
    val = svc.validate_storyboard(pid, "EP01")
    assert val["valid"] is True
    assert env["storyboard"]["skill_excerpt"]


def test_sidecar_rejects_banlist_keeps_a_tier(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    exc = _err(
        lambda: svc.sidecar_add_character(
            pid,
            "EP01",
            SidecarAddCharacterRequest(name="吐槽两位王子"),
            raw={"name": "吐槽两位王子"},
        )
    )
    assert exc.status_code == 422
    assert exc.code == "validation"
    exc2 = _err(
        lambda: svc.sidecar_add_character(
            pid, "EP01", SidecarAddCharacterRequest(name="CURSOR"), raw={"name": "CURSOR"}
        )
    )
    assert exc2.status_code == 422
    env = svc.sidecar_add_character(
        pid,
        "EP01",
        SidecarAddCharacterRequest(name="GPT(CODEX)王子", one_line="A档"),
        raw={"name": "GPT(CODEX)王子"},
    )
    names = [c["name"] for c in env["cast"]["characters"]]
    assert "GPT(CODEX)王子" in names
    assert "吐槽两位王子" not in names


def test_n1_generate_skips_banlist_prefers_spatial_scenes(svc, monkeypatch):
    pid = seed_project_episode(svc)
    persist_and_confirm_intent(svc, pid, lane="female")

    def fake_gen(self, **kw):
        return GeneratedDraft(
            body_md="# 大纲\n- 桥段序列：\n  1. 开钩\n  2. 立规\n  3. 加压\n  4. 主爽\n  5. 集尾\n",
            lane="female",
            shot_cap=12,
            source_skills=[],
            characters=[
                {"name": "程序员", "one_line": "男主"},
                {"name": "豆包", "one_line": "破局"},
                {"name": "吐槽两位王子", "one_line": "脏ACT"},
                {"name": "技术王子", "one_line": "脏TAG"},
                {"name": "幕里两位王子", "one_line": "脏GEN"},
                {"name": "GPT(CODEX)王子", "one_line": "A档"},
                {"name": "Opus5.5(CURSOR)王子", "one_line": "A档"},
            ],
            scenes=[
                {"name": "侧边栏奶茶时刻", "one_line": "陪伴事件"},
                {"name": "开源避难所入口", "one_line": "逃亡动作"},
            ],
        )

    monkeypatch.setattr(FixtureProvider, "generate", fake_gen)
    svc.generate_outline(
        pid, "EP01", OutlineGenerateRequest(lane="female", provider="fixture"), raw={"provider": "fixture"}
    )
    rec = svc._rec(pid, "EP01")
    names = [c["name"] for c in rec["cast"]["characters"]]
    assert "程序员" in names and "豆包" in names
    assert "GPT(CODEX)王子" in names
    assert "Opus5.5(CURSOR)王子" in names
    assert "吐槽两位王子" not in names
    assert "技术王子" not in names
    assert "幕里两位王子" not in names
    scenes = [s["name"] for s in rec["cast"]["scenes"]]
    assert "侧边栏空间" in scenes
    assert "避难所门厅" in scenes
    assert "侧边栏奶茶时刻" not in scenes
    assert "开源避难所入口" not in scenes


def test_materialize_keeps_spatial_scenes_skips_dirty_char():
    cast = {
        "characters": [
            {"id": "CHAR-01", "name": "程序员", "one_line": "男主"},
            {"id": "CHAR-05", "name": "吐槽两位王子", "one_line": "脏"},
        ],
        "scenes": [
            {"id": "SCENE-01", "name": "侧边栏奶茶时刻", "one_line": "陪伴"},
            {"id": "SCENE-02", "name": "开源避难所入口", "one_line": "逃亡"},
            {"id": "SCENE-03", "name": "侧边栏空间", "one_line": "空间"},
        ],
    }
    storyboard = {
        "rows": [
            {"shot_id": "S01", "char_ids": ["CHAR-01"], "scene_id": "SCENE-01"},
            {"shot_id": "S02", "char_ids": ["CHAR-01"], "scene_id": "SCENE-02"},
            {"shot_id": "S03", "char_ids": ["CHAR-01"], "scene_id": "SCENE-03"},
        ]
    }
    characters, scenes, skipped = materialize_cards(cast, storyboard)
    char_ids = {c["id"] for c in characters}
    scene_ids = {s["id"] for s in scenes}
    assert "CHAR-01" in char_ids
    assert "CHAR-05" not in char_ids
    assert {"SCENE-01", "SCENE-02", "SCENE-03"} <= scene_ids
    skipped_scenes = [w for w in skipped if str(w.get("id") or "").startswith("SCENE-")]
    assert not skipped_scenes


def test_class_d_duration_floor_adsorb():
    assert adsorb_duration(5, None, camera="HANDHELD") == (8, None)
    assert adsorb_duration(5, None, camera="WHIP_PUSH") == (8, None)
    assert adsorb_duration(5, None, camera="WHIP_PULL") == (8, None)
    assert adsorb_duration(5, None, camera="ORBIT") == (8, None)
    assert adsorb_duration(5, None, camera="DOLLY_ZOOM") == (8, None)
    assert adsorb_duration(5, None, camera="ROLL") == (8, None)
    assert adsorb_duration(5, None, camera="STATIC") == (5, None)
    assert adsorb_duration(5, None, camera="PUSH") == (5, None)
    assert adsorb_duration(5, "seedance_2", camera="HANDHELD") == (8, "seedance:8")
    assert adsorb_duration(5, "seedance_2", camera="WHIP_PUSH") == (8, "seedance:8")
    assert adsorb_duration(5, "kling", camera="ORBIT") == (10, "kling:10")
    assert adsorb_duration(5, "hailuo", camera="ROLL") == (10, "hailuo:10")
    assert adsorb_duration(5, "veo", camera="DOLLY_ZOOM") == (8, "veo:8")
    row = adsorb_row({"duration_s": 5, "camera": "HANDHELD"}, None)
    assert row["duration_s"] == 8
    assert row["tool_duration_bucket"] is None


def test_class_d_validate_warn_without_profile_hard_with_profile():
    cast = {"characters": [{"id": "CHAR-01", "name": "程序员"}], "scenes": [{"id": "SCENE-01"}]}
    rows = [
        sample_row(
            shot_id="S06",
            seq=6,
            camera="HANDHELD",
            duration_s=5,
            char_ids=["CHAR-01"],
            scene_id="SCENE-01",
            action="手持跟拍",
        )
    ]
    soft = collect_issues(rows, shot_cap=12, tool_profile=None, cast=cast, outline_body="1. 开钩\n")
    floor = [i for i in soft if i["code"] == "duration_below_camera_floor"]
    assert floor and floor[0]["severity"] == "warn"
    assert not any(i.get("severity") == "error" and i["code"] == "duration_below_camera_floor" for i in soft)

    hard = collect_issues(
        rows, shot_cap=12, tool_profile="seedance_2", cast=cast, outline_body="1. 开钩\n"
    )
    floor_hard = [i for i in hard if i["code"] == "duration_below_camera_floor"]
    assert floor_hard and floor_hard[0]["severity"] == "error"


def test_generate_adsorbs_class_d_to_floor(svc, monkeypatch):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    lead = rec["cast"]["characters"][0]["id"]
    scene = rec["cast"]["scenes"][0]["id"]

    def fake_rows(settings, **kw):
        return [
            sample_row(
                shot_id="S01",
                seq=1,
                camera="HANDHELD",
                duration_s=5,
                char_ids=[lead],
                scene_id=scene,
                action="手持跟拍",
            ),
            sample_row(
                shot_id="S02",
                seq=2,
                camera="WHIP_PUSH",
                duration_s=5,
                char_ids=[lead],
                scene_id=scene,
                action="急推破屏",
            ),
            sample_row(
                shot_id="S03",
                seq=3,
                camera="STATIC",
                duration_s=5,
                char_ids=[lead],
                scene_id=scene,
                action="定镜对白",
            ),
        ]

    monkeypatch.setattr("aiv_drama_n2.ops.generate_rows", fake_rows)
    env = svc.generate_storyboard(
        pid,
        "EP01",
        StoryboardGenerateRequest(provider="fixture", tool_profile="seedance_2"),
        raw={"provider": "fixture", "tool_profile": "seedance_2"},
    )
    by_id = {r["shot_id"]: r for r in env["storyboard"]["rows"]}
    assert by_id["S01"]["duration_s"] >= 8
    assert by_id["S02"]["duration_s"] >= 8
    assert by_id["S03"]["duration_s"] == 5
    val = svc.validate_storyboard(pid, "EP01")
    assert not any(i.get("code") == "duration_below_camera_floor" for i in val["issues"])


def test_force_pass_still_forbidden(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    exc = _err(
        lambda: svc.confirm_gate_g2(
            pid, "EP01", {"decision": "pass", "actor": "yangzhou", "force_pass": True}
        )
    )
    assert exc.status_code == 400
    assert exc.code == "force_pass_forbidden"


def test_n3_materialize_spatial_scenes_on_locked_g2(svc, monkeypatch):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    rec["cast"]["scenes"] = [
        {"id": "SCENE-01", "name": "侧边栏奶茶时刻", "one_line": "陪伴", "library_ref": None},
        {"id": "SCENE-02", "name": "开源避难所入口", "one_line": "逃亡", "library_ref": None},
    ]
    lead = rec["cast"]["characters"][0]["id"]

    def fake_rows(settings, **kw):
        return [
            sample_row(shot_id="S01", seq=1, scene_id="SCENE-01", char_ids=[lead]),
            sample_row(shot_id="S02", seq=2, scene_id="SCENE-02", char_ids=[lead], bridge_id="B2"),
        ]

    monkeypatch.setattr("aiv_drama_n2.ops.generate_rows", fake_rows)
    svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    svc.confirm_gate_g2(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    env = svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    scene_ids = {s["id"] for s in env["cards"]["scenes"]}
    assert "SCENE-01" in scene_ids
    assert "SCENE-02" in scene_ids
    skipped = [w for w in (env.get("warnings") or []) if w.get("code") == "b_class_skipped"]
    assert not any(str(w.get("id") or "").startswith("SCENE-") for w in skipped)
