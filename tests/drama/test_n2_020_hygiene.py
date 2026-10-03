"""BRIEF-AIV-020 P0 — named_cast hygiene, duration buckets, skill excerpt/trace.

ForcePass=never. docs≠PASS.
"""

from __future__ import annotations

from aiv_drama.models import SidecarAddCharacterRequest
from aiv_drama_n2.duration import adsorb_duration, adsorb_rows
from aiv_drama_n2.models import StoryboardGenerateRequest
from aiv_drama_n2.named_cast import (
    NAMED_CAST_AUTO_MERGED,
    NAMED_CAST_SIDECAR_ADDED,
    auto_merge_named_cast,
    blocking_named_cast_issues,
    collect_named_hits,
    expand_group,
    extract_paren_entities,
    extract_proper_names,
    fold_brand_to_pool,
    fold_to_attached_name,
    is_bare_brand,
    is_clause_fragment,
    is_dialogue_fragment,
    is_generic_title,
    is_group_label,
    is_registerable_name,
    is_system_speaker,
    names_are_aliases,
    resolve_hit_names,
)
from aiv_drama_n2.skill_evidence import STORYBOARD_GUIDE_PATH, load_storyboard_skill_evidence
from aiv_drama_n2.validate import STORYBOARD_SKILL_PATH

from tests.drama.helpers import lock_g1b, sample_row, seed_project_episode


def _dirty_019_rows(scene: str, lead: str) -> list[dict]:
    """eng-019 pollution shape: system-vo / dirty prefix / verb / group / half-line."""
    return [
        sample_row(
            shot_id="S01",
            seq=1,
            scene_id=scene,
            char_ids=[lead],
            duration_s=2,
            action="求婚式双弹窗弹出",
            dialogue="【系统音】锁定：开始。",
        ),
        sample_row(
            shot_id="S02",
            seq=2,
            scene_id=scene,
            char_ids=[lead],
            duration_s=3,
            action="第二弹窗同步",
            dialogue="/ 【系统音】同步锁定。",
        ),
        sample_row(
            shot_id="S03",
            seq=3,
            scene_id=scene,
            char_ids=[lead],
            duration_s=4,
            action="指出两将军站在门口",
            dialogue=None,
        ),
        sample_row(
            shot_id="S04",
            seq=4,
            scene_id=scene,
            char_ids=[lead],
            duration_s=6,
            action="嘴炮对峙",
            dialogue="两将军：退兵。",
        ),
        sample_row(
            shot_id="S05",
            seq=5,
            scene_id=scene,
            char_ids=["NONE"],
            duration_s=9,
            action="屏幕闪红",
            dialogue="【系统音】协议已启动,目标：锁定",
            notes="空镜/系统音",
        ),
        sample_row(
            shot_id="S06",
            seq=6,
            scene_id=scene,
            char_ids=[lead],
            duration_s=8,
            action="预挂丙将军与预挂丁将军并肩",
            dialogue="预挂丙将军：到齐。",
        ),
    ]


def test_system_voice_and_dirty_prefix_not_registerable():
    assert is_system_speaker("系统音")
    assert is_system_speaker("【系统音】锁定")
    assert is_system_speaker("/ 【系统音】同步")
    assert not is_registerable_name("【系统音】锁定")
    assert not is_registerable_name("/ 【系统音】同步")
    assert not is_registerable_name("【系统音】协议已启动,目标")
    assert not is_registerable_name("指出两将军")
    assert not is_registerable_name("两将军")
    assert is_registerable_name("预挂丙将军")
    assert is_registerable_name("预挂丁将军")
    assert is_registerable_name("预挂甲")
    assert not is_bare_brand("预挂甲")
    assert is_dialogue_fragment("你被双将军")
    assert is_dialogue_fragment("而是两将军")
    assert not is_registerable_name("你被双将军")
    assert not is_registerable_name("而是两将军")
    assert is_generic_title("王国王子")
    assert is_generic_title("AI将军")
    assert not is_registerable_name("王国王子")
    assert not is_registerable_name("AI将军")
    assert is_clause_fragment("预挂乙当众拆穿两个将军")
    assert is_clause_fragment("预挂乙的随从反制两个将军")
    assert is_group_label("两侧将军") or is_generic_title("两侧将军")
    assert not is_registerable_name("预挂乙当众拆穿两个将军")
    assert not is_registerable_name("预挂乙的随从反制两个将军")
    assert not is_registerable_name("两侧将军")


def test_collect_hits_skips_b_class_keeps_titled():
    rows = _dirty_019_rows("SCENE-01", "CHAR-01")
    hits = collect_named_hits(
        rows,
        cast={"characters": [{"id": "CHAR-01", "name": "预挂甲"}]},
        outline_body="预挂丙将军与预挂丁将军出场",
    )
    names = {h["name"] for h in hits}
    assert "【系统音】锁定" not in names
    assert "/ 【系统音】同步" not in names
    assert "【系统音】协议已启动,目标" not in names
    assert "预挂丙将军" in names
    assert "预挂丁将军" in names
    assert "两将军" in names or "指出两将军" in names


def test_auto_merge_skips_system_voice_half_line_adds_titled():
    rec = {
        "outline": {"body_md": "1. 开钩\n预挂丙将军与预挂丁将军出场\n"},
        "cast": {
            "characters": [{"id": "CHAR-01", "name": "预挂甲"}, {"id": "CHAR-02", "name": "预挂乙"}],
            "scenes": [{"id": "SCENE-01"}],
            "version": 3,
            "locked": True,
        },
        "gate": {"locked": True, "last_decision": "pass"},
    }
    n = {"i": 2}

    def alloc(_rec):
        n["i"] += 1
        return f"CHAR-{n['i']:02d}"

    rows, added = auto_merge_named_cast(rec, _dirty_019_rows("SCENE-01", "CHAR-01"), alloc_char=alloc)
    names = {c["name"] for c in rec["cast"]["characters"]}
    assert "预挂丙将军" in names
    assert "预挂丁将军" in names
    assert "【系统音】锁定" not in names
    assert "指出两将军" not in names
    assert "两将军" not in names
    assert "【系统音】协议已启动,目标" not in names
    assert rec["cast"]["version"] == 4
    by_name = {c["name"]: c["id"] for c in rec["cast"]["characters"]}
    wired = {r["shot_id"]: r for r in rows}
    assert by_name["预挂丙将军"] in wired["S06"]["char_ids"]
    assert by_name["预挂丁将军"] in wired["S06"]["char_ids"]
    assert by_name["预挂丙将军"] in wired["S04"]["char_ids"]
    assert by_name["预挂丁将军"] in wired["S04"]["char_ids"]
    assert by_name["预挂丙将军"] not in wired["S01"]["char_ids"]
    assert added


def test_generate_hygiene_and_observability(svc, monkeypatch):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    rec["outline"]["body_md"] = rec["outline"]["body_md"] + "\n预挂丙将军 / 预挂丁将军出场\n"
    outline_body = rec["outline"]["body_md"]
    outline_ver = rec["outline"]["version"]
    cast_ver = rec["cast"]["version"]
    lead = rec["cast"]["characters"][0]["id"]
    scene = rec["cast"]["scenes"][0]["id"]

    def fake_rows(settings, **kw):
        return _dirty_019_rows(scene, lead)

    monkeypatch.setattr("aiv_drama_n2.ops.generate_rows", fake_rows)
    env = svc.generate_storyboard(
        pid, "EP01", StoryboardGenerateRequest(provider="llm"), raw={"provider": "llm"}
    )
    rec = svc._rec(pid, "EP01")
    names = {c["name"] for c in rec["cast"]["characters"]}
    assert "预挂丙将军" in names
    assert "预挂丁将军" in names
    assert not any("系统音" in n for n in names)
    assert "两将军" not in names
    assert "指出两将军" not in names
    assert rec["cast"]["version"] == cast_ver + 1
    assert rec["gate"]["locked"] is True
    assert rec["outline"]["body_md"] == outline_body
    assert rec["outline"]["version"] == outline_ver
    assert rec["episode"]["locks"]["g1b"] is True
    codes = {w["code"] for w in env.get("validate_warnings") or []}
    assert NAMED_CAST_AUTO_MERGED in codes
    got = svc.get_storyboard(pid, "EP01")
    assert any(w["code"] == NAMED_CAST_AUTO_MERGED for w in got.get("validate_warnings") or [])
    val = svc.validate_storyboard(pid, "EP01")
    assert any(i["code"] == NAMED_CAST_AUTO_MERGED for i in val["issues"])
    assert blocking_named_cast_issues(val["issues"]) == []
    assert val["valid"] is True


def test_sidecar_warn_visible_on_get_validate_keeps_g1b(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    outline_body = rec["outline"]["body_md"]
    env = svc.sidecar_add_character(
        pid,
        "EP01",
        SidecarAddCharacterRequest(name="预挂丙将军", one_line="侧车配角"),
        raw={"name": "预挂丙将军"},
    )
    rec = svc._rec(pid, "EP01")
    assert rec["gate"]["locked"] is True
    assert rec["outline"]["body_md"] == outline_body
    assert env.get("cast_changed") is True
    svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    got = svc.get_storyboard(pid, "EP01")
    codes = {w["code"] for w in got.get("validate_warnings") or []}
    assert NAMED_CAST_SIDECAR_ADDED in codes or NAMED_CAST_AUTO_MERGED in codes
    val = svc.validate_storyboard(pid, "EP01")
    val_codes = {i["code"] for i in val["issues"]}
    assert NAMED_CAST_SIDECAR_ADDED in val_codes or NAMED_CAST_AUTO_MERGED in val_codes
    assert blocking_named_cast_issues(val["issues"]) == []


def test_duration_adsorb_default_ladder():
    assert adsorb_duration(2, None) == (5, None)
    assert adsorb_duration(3, None) == (5, None)
    assert adsorb_duration(4, None) == (5, None)
    assert adsorb_duration(6, None) == (5, None)
    assert adsorb_duration(7, None) == (8, None)
    assert adsorb_duration(8, None) == (8, None)
    assert adsorb_duration(9, None) == (10, None)
    assert adsorb_duration(10, None) == (10, None)


def test_duration_hard_adsorb_profile_no_collision():
    assert adsorb_duration(2, "seedance_2") == (5, "seedance:5")
    assert adsorb_duration(7, "seedance_2") == (8, "seedance:8")
    assert adsorb_duration(9, "seedance_2") == (10, "seedance:10")
    assert adsorb_duration(5, "kling") == (5, "kling:5")
    assert adsorb_duration(8, "kling") == (10, "kling:10")
    assert adsorb_duration(5, "hailuo") == (6, "hailuo:6")
    assert adsorb_duration(8, "hailuo") == (10, "hailuo:10")
    assert adsorb_duration(3, "veo") == (8, "veo:8")
    rows = adsorb_rows(
        [{"duration_s": 2, "tool_duration_bucket": "3s"}, {"duration_s": 9, "tool_duration_bucket": "4s"}],
        "seedance_2",
    )
    assert rows[0]["duration_s"] == 5 and rows[0]["tool_duration_bucket"] == "seedance:5"
    assert rows[1]["duration_s"] == 10 and rows[1]["tool_duration_bucket"] == "seedance:10"


def test_generate_adsorbs_durations_when_profile_unset(svc, monkeypatch):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    lead = rec["cast"]["characters"][0]["id"]
    scene = rec["cast"]["scenes"][0]["id"]

    def fake_rows(settings, **kw):
        return _dirty_019_rows(scene, lead)

    monkeypatch.setattr("aiv_drama_n2.ops.generate_rows", fake_rows)
    env = svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    durations = [r["duration_s"] for r in env["storyboard"]["rows"]]
    assert durations
    assert all(d in {5, 8, 10} for d in durations)
    assert all(r.get("tool_duration_bucket") is None for r in env["storyboard"]["rows"])


def test_generate_hard_adsorb_when_profile_selected(svc, monkeypatch):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    lead = rec["cast"]["characters"][0]["id"]
    scene = rec["cast"]["scenes"][0]["id"]

    def fake_rows(settings, **kw):
        return _dirty_019_rows(scene, lead)

    monkeypatch.setattr("aiv_drama_n2.ops.generate_rows", fake_rows)
    env = svc.generate_storyboard(
        pid,
        "EP01",
        StoryboardGenerateRequest(provider="fixture", tool_profile="seedance_2"),
        raw={"provider": "fixture", "tool_profile": "seedance_2"},
    )
    for row in env["storyboard"]["rows"]:
        assert row["duration_s"] in {5, 8, 10}
        assert row["tool_duration_bucket"] == f"seedance:{row['duration_s']}"
    val = svc.validate_storyboard(pid, "EP01")
    assert not any(i.get("code") == "duration_bucket_mismatch" for i in val["issues"])


def test_skill_excerpt_and_trace_persist_on_generate_get_validate(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    env = svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    assert STORYBOARD_SKILL_PATH in (env.get("skill_paths") or [])
    assert STORYBOARD_GUIDE_PATH in (env.get("skill_paths") or [])
    assert env.get("skill_excerpt")
    assert "动态漫" in env["skill_excerpt"] or env["skill_excerpt"].startswith("###")
    trace = env.get("skill_trace") or {}
    assert trace.get("paths")
    assert trace.get("excerpts")
    assert trace["excerpts"][0].get("sha256")
    assert env.get("n2_request", {}).get("skill_excerpt")
    assert env["n2_request"]["skill_paths"]
    rec = svc._rec(pid, "EP01")
    assert rec["storyboard"]["skill_excerpt"]
    assert rec["n2_request"]["skill_trace"]["injected"] is True
    got = svc.get_storyboard(pid, "EP01")
    assert got.get("skill_excerpt")
    assert got.get("skill_trace", {}).get("excerpts")
    assert got.get("n2_request", {}).get("skill_paths")
    val = svc.validate_storyboard(pid, "EP01")
    assert val.get("skill_excerpt")
    assert val.get("skill_trace", {}).get("paths")
    assert val.get("n2_request", {}).get("skill_excerpt")
    evidence = load_storyboard_skill_evidence(svc.settings)
    assert STORYBOARD_SKILL_PATH in evidence["paths"]
    assert STORYBOARD_GUIDE_PATH in evidence["paths"]


def _eng020_half_line_rows(scene: str, lead: str, support: str) -> list[dict]:
    return [
        sample_row(
            shot_id="S04",
            seq=4,
            scene_id=scene,
            char_ids=[lead, support],
            action="两大王国将军同时现身茶水间",
            dialogue="你被双将军围住了？",
        ),
        sample_row(
            shot_id="S11",
            seq=11,
            scene_id=scene,
            char_ids=[lead],
            action="停战现场",
            dialogue="不是追杀，而是两将军同时伸出手。",
        ),
        sample_row(
            shot_id="S05",
            seq=5,
            scene_id=scene,
            char_ids=[lead],
            action="预挂丙将军与预挂丁将军对峙",
            dialogue="预挂丙将军：到齐。",
        ),
    ]


def test_half_line_fragments_never_open_char():
    rec = {
        "outline": {
            "body_md": "1. 开钩\n预挂丙将军与预挂丁将军出场\n两大王国将军\n"
        },
        "cast": {
            "characters": [
                {"id": "CHAR-01", "name": "预挂甲"},
                {"id": "CHAR-02", "name": "预挂乙"},
            ],
            "scenes": [{"id": "SCENE-01"}],
            "version": 3,
            "locked": True,
        },
        "gate": {"locked": True, "last_decision": "pass"},
    }
    n = {"i": 2}

    def alloc(_rec):
        n["i"] += 1
        return f"CHAR-{n['i']:02d}"

    rows, added = auto_merge_named_cast(
        rec, _eng020_half_line_rows("SCENE-01", "CHAR-01", "CHAR-02"), alloc_char=alloc
    )
    names = {c["name"] for c in rec["cast"]["characters"]}
    assert "预挂甲" in names and "预挂乙" in names
    assert "预挂丙将军" in names
    assert "预挂丁将军" in names
    assert "你被双将军" not in names
    assert "而是两将军" not in names
    assert "王国王子" not in names
    assert "AI将军" not in names
    by_name = {c["name"]: c["id"] for c in rec["cast"]["characters"]}
    wired = {r["shot_id"]: r for r in rows}
    for shot in ("S04", "S11"):
        ids = wired[shot]["char_ids"]
        assert by_name["预挂丙将军"] in ids
        assert by_name["预挂丁将军"] in ids
        assert "CHAR-01" in ids
        assert all(by_name.get(dirty) not in ids for dirty in ("你被双将军", "而是两将军", "王国王子", "AI将军"))
        assert all(cid in by_name.values() for cid in ids if cid != "NONE")
    assert added


def test_full_dialogue_group_maps_to_titled_slots():
    assert expand_group("双将军", ["预挂丙将军", "预挂丁将军", "预挂甲"]) == ["预挂丙将军", "预挂丁将军"]
    hits = collect_named_hits(
        [
            {
                "shot_id": "S04",
                "action": "茶水间对峙",
                "dialogue": "你被双将军围住了？",
                "char_ids": ["CHAR-01"],
            }
        ],
        cast={
            "characters": [
                {"id": "CHAR-01", "name": "预挂甲"},
                {"id": "CHAR-04", "name": "预挂丙将军"},
                {"id": "CHAR-05", "name": "预挂丁将军"},
            ]
        },
        outline_body="预挂丙将军 / 预挂丁将军",
    )
    names = {h["name"] for h in hits}
    assert "你被双将军" not in names
    assert "双将军" in names
    resolved = {h["name"] for h in hits if h.get("registerable")}
    assert "预挂丙将军" in resolved or "双将军" in names


def test_generate_skips_half_line_and_generic_titles(svc, monkeypatch):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    rec["outline"]["body_md"] = rec["outline"]["body_md"] + "\n预挂丙将军与预挂丁将军\n"
    lead = rec["cast"]["characters"][0]["id"]
    support = rec["cast"]["characters"][1]["id"]
    scene = rec["cast"]["scenes"][0]["id"]
    leads = {rec["cast"]["characters"][0]["name"], rec["cast"]["characters"][1]["name"]}

    def fake_rows(settings, **kw):
        return _eng020_half_line_rows(scene, lead, support)

    monkeypatch.setattr("aiv_drama_n2.ops.generate_rows", fake_rows)
    env = svc.generate_storyboard(
        pid, "EP01", StoryboardGenerateRequest(provider="llm"), raw={"provider": "llm"}
    )
    rec = svc._rec(pid, "EP01")
    names = {c["name"] for c in rec["cast"]["characters"]}
    assert leads <= names
    assert "预挂丙将军" in names
    assert "预挂丁将军" in names
    assert "你被双将军" not in names
    assert "而是两将军" not in names
    assert "王国王子" not in names
    assert "AI将军" not in names
    by_name = {c["name"]: c["id"] for c in rec["cast"]["characters"]}
    rows = {r["shot_id"]: r for r in env["storyboard"]["rows"]}
    for shot in ("S04", "S11"):
        ids = rows[shot]["char_ids"]
        assert by_name["预挂丙将军"] in ids
        assert by_name["预挂丁将军"] in ids
        assert lead in ids
        assert all(cid in {c["id"] for c in rec["cast"]["characters"]} for cid in ids)
    assert env["storyboard"]["skill_excerpt"]
    durations = [r["duration_s"] for r in env["storyboard"]["rows"]]
    assert all(d in {5, 8, 10} for d in durations)


def _prefix_fold_rows(scene: str, lead: str) -> list[dict]:
    return [
        sample_row(
            shot_id="S01",
            seq=1,
            scene_id=scene,
            char_ids=[lead],
            action="求婚式双弹窗弹出",
            dialogue="【系统音】锁定：开始。",
        ),
        sample_row(
            shot_id="S07",
            seq=7,
            scene_id=scene,
            char_ids=[lead],
            action="茶水间对峙",
            dialogue="小预挂丙将军：同步锁定。",
        ),
        sample_row(
            shot_id="S08",
            seq=8,
            scene_id=scene,
            char_ids=[lead],
            action="预挂丁将军挡在门口",
            dialogue="预挂丁将军：到齐。",
        ),
        sample_row(
            shot_id="S09",
            seq=9,
            scene_id=scene,
            char_ids=[lead],
            action="嘴炮对峙",
            dialogue="两将军：退兵。",
        ),
    ]


def test_prefix_suffix_folds_onto_attached_only():
    pool = ["预挂丙将军", "预挂丁将军", "预挂甲"]
    assert fold_to_attached_name("小预挂丙将军", pool) == "预挂丙将军"
    assert fold_brand_to_pool("预挂丁将军大人", pool) == "预挂丁将军"
    assert fold_to_attached_name("预挂戊", pool) is None
    assert names_are_aliases("小预挂丙将军", "预挂丙将军")
    assert names_are_aliases("预挂丁将军大人", "预挂丁将军")
    assert not names_are_aliases("预挂戊", "预挂丙将军")
    assert resolve_hit_names("小预挂丙将军", pool) == ["预挂丙将军"]
    assert fold_brand_to_pool("预挂戊", pool) is None


def test_paren_wrap_is_one_entity_not_two_rows():
    names = extract_proper_names("Jia（预挂丙将军）与Yi（预挂丁将军）出场")
    assert "Jia" not in names
    assert "Yi" not in names
    assert names.count("预挂丙将军") == 1
    assert names.count("预挂丁将军") == 1
    glued = extract_paren_entities("Jia（预挂丙将军）站在门口")
    assert glued == ["预挂丙将军"]
    titled = extract_proper_names("预挂丙将军与预挂丁将军并肩")
    assert "预挂丙将军" in titled
    assert "预挂丁将军" in titled


def test_auto_merge_folds_prefix_no_orphan_no_paren_split():
    rec = {
        "outline": {
            "body_md": "1. 开钩\nJia（预挂丙将军）与预挂丁将军出场\n两大王国将军\n"
        },
        "cast": {
            "characters": [
                {"id": "CHAR-01", "name": "预挂甲"},
                {"id": "CHAR-02", "name": "预挂乙"},
                {"id": "CHAR-03", "name": "预挂丙将军"},
            ],
            "scenes": [{"id": "SCENE-01"}],
            "version": 3,
            "locked": True,
        },
        "gate": {"locked": True, "last_decision": "pass"},
    }
    n = {"i": 3}

    def alloc(_rec):
        n["i"] += 1
        return f"CHAR-{n['i']:02d}"

    rows, added = auto_merge_named_cast(
        rec, _prefix_fold_rows("SCENE-01", "CHAR-01"), alloc_char=alloc
    )
    names = [c["name"] for c in rec["cast"]["characters"]]
    assert "小预挂丙将军" not in names
    assert names.count("预挂丙将军") == 1
    assert "预挂丁将军" in names
    assert "你被双将军" not in names
    by_name = {c["name"]: c["id"] for c in rec["cast"]["characters"]}
    bing_id = by_name["预挂丙将军"]
    ding_id = by_name["预挂丁将军"]
    wired = {r["shot_id"]: r for r in rows}
    assert bing_id in wired["S07"]["char_ids"]
    assert ding_id in wired["S08"]["char_ids"]
    assert bing_id in wired["S09"]["char_ids"]
    assert ding_id in wired["S09"]["char_ids"]
    assert bing_id not in wired["S01"]["char_ids"]
    hung = {cid for r in rows for cid in r["char_ids"]}
    assert bing_id in hung and ding_id in hung
    assert added


def test_generate_folds_prefix_and_hangs_titled(svc, monkeypatch):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    rec["outline"]["body_md"] = rec["outline"]["body_md"] + "\nJia（预挂丙将军）与预挂丁将军\n"
    svc._register_char(rec, "CHAR-03")
    rec["cast"]["characters"].append({"id": "CHAR-03", "name": "预挂丙将军", "one_line": "已挂", "library_ref": None})
    lead = rec["cast"]["characters"][0]["id"]
    scene = rec["cast"]["scenes"][0]["id"]
    leads = {rec["cast"]["characters"][0]["name"], rec["cast"]["characters"][1]["name"]}

    def fake_rows(settings, **kw):
        return _prefix_fold_rows(scene, lead)

    monkeypatch.setattr("aiv_drama_n2.ops.generate_rows", fake_rows)
    env = svc.generate_storyboard(
        pid, "EP01", StoryboardGenerateRequest(provider="llm"), raw={"provider": "llm"}
    )
    rec = svc._rec(pid, "EP01")
    names = [c["name"] for c in rec["cast"]["characters"]]
    assert leads <= set(names)
    assert "小预挂丙将军" not in names
    assert names.count("预挂丙将军") == 1
    assert "预挂丁将军" in names
    by_name = {c["name"]: c["id"] for c in rec["cast"]["characters"]}
    bing_id = by_name["预挂丙将军"]
    ding_id = by_name["预挂丁将军"]
    rows = {r["shot_id"]: r for r in env["storyboard"]["rows"]}
    assert bing_id in rows["S07"]["char_ids"]
    assert ding_id in rows["S08"]["char_ids"]
    assert bing_id in rows["S09"]["char_ids"] and ding_id in rows["S09"]["char_ids"]
    hung = {cid for r in env["storyboard"]["rows"] for cid in r["char_ids"]}
    assert bing_id in hung and ding_id in hung
    durations = [r["duration_s"] for r in env["storyboard"]["rows"]]
    assert all(d in {5, 8, 10} for d in durations)
    assert env["storyboard"]["skill_excerpt"]
    assert env.get("skill_paths")


def _eng020r4_clause_rows(scene: str, lead: str) -> list[dict]:
    return [
        sample_row(
            shot_id="S10",
            seq=10,
            scene_id=scene,
            char_ids=[lead],
            action="预挂乙当众拆穿两个将军",
            dialogue="两侧将军：退兵。",
        ),
        sample_row(
            shot_id="S11",
            seq=11,
            scene_id=scene,
            char_ids=[lead],
            action="预挂乙的随从反制两个将军",
            dialogue="你被双将军围住了？",
        ),
        sample_row(
            shot_id="S12",
            seq=12,
            scene_id=scene,
            char_ids=[lead],
            action="茶水间对峙",
            dialogue="预挂丙将军：到齐。",
        ),
    ]


def test_clause_fragments_and_side_generic_never_open_char():
    assert "预挂乙当众拆穿两个将军" not in extract_proper_names("预挂乙当众拆穿两个将军")
    assert "预挂乙的随从反制两个将军" not in extract_proper_names("预挂乙的随从反制两个将军")
    assert expand_group("两侧将军", ["预挂丙将军", "预挂丁将军", "预挂甲", "预挂乙"]) == [
        "预挂丙将军",
        "预挂丁将军",
    ]
    assert resolve_hit_names("两侧将军", ["预挂丙将军", "预挂丁将军", "预挂甲"]) == [
        "预挂丙将军",
        "预挂丁将军",
    ]
    hits = collect_named_hits(
        _eng020r4_clause_rows("SCENE-01", "CHAR-01"),
        cast={
            "characters": [
                {"id": "CHAR-01", "name": "预挂甲"},
                {"id": "CHAR-02", "name": "预挂乙"},
                {"id": "CHAR-03", "name": "预挂丙将军"},
                {"id": "CHAR-04", "name": "预挂丁将军"},
            ]
        },
        outline_body="预挂丙将军与预挂丁将军\n预挂乙当众拆穿两个将军\n",
    )
    names = {h["name"] for h in hits}
    assert "预挂乙当众拆穿两个将军" not in names
    assert "预挂乙的随从反制两个将军" not in names
    assert "两侧将军" in names or "两将军" in names or "双将军" in names or "两个将军" in names
    registerable = {h["name"] for h in hits if h.get("registerable")}
    assert "两侧将军" not in registerable
    assert "预挂丙将军" in registerable or "两侧将军" in names


def test_auto_merge_rejects_clause_fragments_hangs_titled():
    rec = {
        "outline": {
            "body_md": (
                "1. 开钩\n预挂丙将军与预挂丁将军出场\n"
                "预挂乙当众拆穿两个将军\n预挂乙的随从反制两个将军\n两侧将军对峙\n"
            )
        },
        "cast": {
            "characters": [
                {"id": "CHAR-01", "name": "预挂甲"},
                {"id": "CHAR-02", "name": "预挂乙"},
            ],
            "scenes": [{"id": "SCENE-01"}],
            "version": 3,
            "locked": True,
        },
        "gate": {"locked": True, "last_decision": "pass"},
    }
    n = {"i": 2}

    def alloc(_rec):
        n["i"] += 1
        return f"CHAR-{n['i']:02d}"

    rows, added = auto_merge_named_cast(
        rec, _eng020r4_clause_rows("SCENE-01", "CHAR-01"), alloc_char=alloc
    )
    names = [c["name"] for c in rec["cast"]["characters"]]
    assert "预挂甲" in names and "预挂乙" in names
    assert "预挂乙当众拆穿两个将军" not in names
    assert "预挂乙的随从反制两个将军" not in names
    assert "两侧将军" not in names
    assert "两将军" not in names
    assert "双将军" not in names
    assert "你被双将军" not in names
    assert "预挂丙将军" in names
    assert "预挂丁将军" in names
    by_name = {c["name"]: c["id"] for c in rec["cast"]["characters"]}
    bing_id = by_name["预挂丙将军"]
    ding_id = by_name["预挂丁将军"]
    wired = {r["shot_id"]: r for r in rows}
    assert bing_id in wired["S10"]["char_ids"]
    assert ding_id in wired["S10"]["char_ids"]
    assert bing_id in wired["S11"]["char_ids"]
    assert ding_id in wired["S11"]["char_ids"]
    hung = {cid for r in rows for cid in r["char_ids"]}
    assert bing_id in hung and ding_id in hung
    assert added


def test_generate_skips_clause_fragments_keeps_duration_skill(svc, monkeypatch):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    rec["outline"]["body_md"] = (
        rec["outline"]["body_md"]
        + "\n预挂丙将军与预挂丁将军\n预挂乙当众拆穿两个将军\n预挂乙的随从反制两个将军\n"
    )
    lead = rec["cast"]["characters"][0]["id"]
    scene = rec["cast"]["scenes"][0]["id"]
    leads = {rec["cast"]["characters"][0]["name"], rec["cast"]["characters"][1]["name"]}

    def fake_rows(settings, **kw):
        return _eng020r4_clause_rows(scene, lead)

    monkeypatch.setattr("aiv_drama_n2.ops.generate_rows", fake_rows)
    env = svc.generate_storyboard(
        pid, "EP01", StoryboardGenerateRequest(provider="llm"), raw={"provider": "llm"}
    )
    rec = svc._rec(pid, "EP01")
    names = [c["name"] for c in rec["cast"]["characters"]]
    assert leads <= set(names)
    assert "预挂乙当众拆穿两个将军" not in names
    assert "预挂乙的随从反制两个将军" not in names
    assert "两侧将军" not in names
    assert "你被双将军" not in names
    assert "预挂丙将军" in names
    assert "预挂丁将军" in names
    by_name = {c["name"]: c["id"] for c in rec["cast"]["characters"]}
    bing_id = by_name["预挂丙将军"]
    ding_id = by_name["预挂丁将军"]
    rows = {r["shot_id"]: r for r in env["storyboard"]["rows"]}
    assert bing_id in rows["S10"]["char_ids"] and ding_id in rows["S10"]["char_ids"]
    hung = {cid for r in env["storyboard"]["rows"] for cid in r["char_ids"]}
    assert bing_id in hung and ding_id in hung
    durations = [r["duration_s"] for r in env["storyboard"]["rows"]]
    assert all(d in {5, 8, 10} for d in durations)
    assert env["storyboard"]["skill_excerpt"]
    assert env.get("skill_paths")
