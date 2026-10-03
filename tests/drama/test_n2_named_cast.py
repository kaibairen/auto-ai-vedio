"""BRIEF-AIV-017a · CAST — O1 auto-merge, O2 sidecar, O5 warn vs G2 block. ForcePass=never."""

from __future__ import annotations

from aiv_drama.errors import AppError
from aiv_drama.models import SidecarAddCharacterRequest
from aiv_drama_n2.models import StoryboardGenerateRequest, StoryboardWrite
from aiv_drama_n2.named_cast import (
    NAMED_CAST_GATE,
    NAMED_CAST_MISSING,
    auto_merge_named_cast,
    apply_char_id_wiring,
    blocking_named_cast_issues,
    collect_named_hits,
    expand_group,
    extract_speakers,
    prune_dirty_char_ids,
    resolve_hit_names,
    resolve_to_pool_name,
)
from aiv_drama_n2.validate import collect_issues, issue

from tests.drama.helpers import lock_g1b, sample_row, seed_project_episode


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def _write(rows, **kw):
    return StoryboardWrite.model_validate({"rows": rows, **kw})


def _prince_rows(scene: str, lead: str) -> list[dict]:
    return [
        sample_row(
            shot_id="S01",
            seq=1,
            scene_id=scene,
            char_ids=[lead],
            action="求婚式弹窗弹出",
            dialogue="CODEX王子：嫁给我。",
        ),
        sample_row(
            shot_id="S02",
            seq=2,
            scene_id=scene,
            char_ids=[lead],
            action="OPUS5.5王子破屏而入",
            dialogue=None,
        ),
        sample_row(
            shot_id="S03",
            seq=3,
            scene_id=scene,
            char_ids=[lead],
            action="身后两位王子怒吼追来",
            dialogue="王子们：给我追！",
        ),
        sample_row(
            shot_id="S04",
            seq=4,
            scene_id=scene,
            char_ids=["NONE"],
            action="屏幕闪红",
            dialogue="系统音：通缉令发布。",
            notes="空镜/系统音",
        ),
    ]


def test_extract_speakers_and_groups():
    assert extract_speakers("CODEX王子：嫁给我。") == ["CODEX王子"]
    assert extract_speakers("系统音：通缉令发布。") == ["系统音"]
    hits = collect_named_hits(
        [
            {
                "shot_id": "S01",
                "action": "OPUS5.5王子破屏而入",
                "dialogue": "CODEX王子：站住",
                "char_ids": [],
            },
            {
                "shot_id": "S02",
                "action": "王子们追来",
                "dialogue": None,
                "char_ids": [],
            },
        ]
    )
    names = {h["name"] for h in hits}
    assert "CODEX王子" in names
    assert "OPUS5.5王子" in names
    assert "王子们" in names
    assert expand_group("王子们", ["CODEX王子", "OPUS5.5王子", "林晚"]) == ["CODEX王子", "OPUS5.5王子"]


def test_collect_issues_system_vo_not_named_cast():
    rows = [
        sample_row(
            char_ids=["NONE"],
            scene_id="SCENE-01",
            action="屏幕闪红",
            dialogue="系统音：通缉令发布。",
            notes="空镜/系统音",
        )
    ]
    issues = collect_issues(
        rows,
        shot_cap=12,
        tool_profile=None,
        cast={"characters": [{"id": "CHAR-01", "name": "林晚"}], "scenes": [{"id": "SCENE-01"}]},
        named_cast_check="warn",
    )
    assert not blocking_named_cast_issues(issues)


def test_o1_auto_merge_on_generate_keeps_g1b_and_outline(svc, monkeypatch):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    outline_body = rec["outline"]["body_md"]
    outline_ver = rec["outline"]["version"]
    cast_ver = rec["cast"]["version"]
    confirmed = rec["outline"]["confirmed_by"]

    def fake_rows(settings, **kw):
        scene = (kw["cast"].get("scenes") or [{}])[0].get("id") or "SCENE-01"
        lead = (kw["cast"].get("characters") or [{}])[0].get("id") or "CHAR-01"
        return _prince_rows(scene, lead)

    monkeypatch.setattr("aiv_drama_n2.ops.generate_rows", fake_rows)
    env = svc.generate_storyboard(
        pid, "EP01", StoryboardGenerateRequest(provider="llm"), raw={"provider": "llm"}
    )
    rec = svc._rec(pid, "EP01")
    by_name = {c["name"]: c["id"] for c in rec["cast"]["characters"]}
    assert "CODEX王子" in by_name
    assert "OPUS5.5王子" in by_name
    assert "王子们" not in by_name
    assert "系统音" not in by_name
    assert rec["cast"]["version"] == cast_ver + 1
    assert rec["cast"]["locked"] is True
    assert rec["gate"]["locked"] is True
    assert rec["gate"]["last_decision"] == "pass"
    assert rec["outline"]["locked"] is True
    assert rec["outline"]["confirmed_by"] == confirmed
    assert rec["outline"]["body_md"] == outline_body
    assert rec["outline"]["version"] == outline_ver
    assert rec["episode"]["locks"]["g1b"] is True
    assert rec["episode"]["status"] == "locked_g1b"
    rows = {r["shot_id"]: r for r in env["storyboard"]["rows"]}
    assert by_name["CODEX王子"] in rows["S01"]["char_ids"]
    assert by_name["OPUS5.5王子"] in rows["S02"]["char_ids"]
    assert by_name["CODEX王子"] in rows["S03"]["char_ids"]
    assert by_name["OPUS5.5王子"] in rows["S03"]["char_ids"]
    assert env.get("cast_changed") is True
    assert any(w["code"] == "named_cast_auto_merged" for w in env.get("validate_warnings") or [])
    val = svc.validate_storyboard(pid, "EP01")
    assert val["valid"] is True
    assert blocking_named_cast_issues(val["issues"]) == []
    gate = svc.confirm_gate_g2(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    assert gate["gate"]["locked"] is True
    assert rec["outline"]["body_md"] == outline_body


def test_o2_sidecar_add_does_not_unlock_g1b_or_rewrite_outline(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    outline_body = rec["outline"]["body_md"]
    outline_ver = rec["outline"]["version"]
    cast_ver = rec["cast"]["version"]
    env = svc.sidecar_add_character(
        pid,
        "EP01",
        SidecarAddCharacterRequest(name="CODEX王子", one_line="弹窗反派", actor="yangzhou"),
        raw={"name": "CODEX王子", "one_line": "弹窗反派"},
    )
    rec = svc._rec(pid, "EP01")
    assert rec["gate"]["locked"] is True
    assert rec["gate"]["last_decision"] == "pass"
    assert rec["outline"]["locked"] is True
    assert rec["outline"]["body_md"] == outline_body
    assert rec["outline"]["version"] == outline_ver
    assert rec["cast"]["locked"] is True
    assert rec["cast"]["confirmed_by"]
    assert rec["cast"]["version"] == cast_ver + 1
    assert rec["episode"]["locks"]["g1b"] is True
    assert rec["episode"]["status"] == "locked_g1b"
    assert rec["episode"]["next_edges"] == ["D-N2"]
    assert env.get("cast_changed") is True
    assert any(h.get("code") == "cast_changed" for h in env.get("hints") or [])
    prince = next(c for c in rec["cast"]["characters"] if c["name"] == "CODEX王子")
    assert prince["one_line"] == "弹窗反派"
    again = svc.sidecar_add_character(
        pid, "EP01", SidecarAddCharacterRequest(name="CODEX王子"), raw={"name": "CODEX王子"}
    )
    assert again["cast"]["version"] == rec["cast"]["version"]
    assert sum(1 for c in again["cast"]["characters"] if c["name"] == "CODEX王子") == 1


def test_o5_warn_valid_but_g2_product_gate_blocks(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    scene = rec["cast"]["scenes"][0]["id"]
    lead = rec["cast"]["characters"][0]["id"]
    names_before = {c["name"] for c in rec["cast"]["characters"]}
    rows = [
        sample_row(
            scene_id=scene,
            char_ids=[lead],
            action="弹窗弹出",
            dialogue="CODEX王子：嫁给我。",
        )
    ]
    env = svc.put_storyboard(pid, "EP01", _write(rows), raw={"rows": rows})
    assert env["ok"] is True
    assert "CODEX王子" not in {c["name"] for c in svc._rec(pid, "EP01")["cast"]["characters"]}
    assert {c["name"] for c in svc._rec(pid, "EP01")["cast"]["characters"]} == names_before
    codes = {w["code"] for w in env.get("validate_warnings") or []}
    assert NAMED_CAST_MISSING in codes
    val = svc.validate_storyboard(pid, "EP01")
    assert val["valid"] is True
    assert any(i["code"] == NAMED_CAST_MISSING and i["severity"] == "warn" for i in val["issues"])
    exc = _err(lambda: svc.confirm_gate_g2(pid, "EP01", {"decision": "pass", "actor": "yangzhou"}))
    assert exc.status_code == 422
    assert exc.code == NAMED_CAST_GATE
    assert "具名" in exc.message
    rec = svc._rec(pid, "EP01")
    assert rec["gate_g2"]["locked"] is False
    assert rec["storyboard"]["locked"] is False


def test_o5_error_mode_hard_fail_on_put(svc):
    object.__setattr__(svc.settings, "named_cast_check", "error")
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    scene = rec["cast"]["scenes"][0]["id"]
    lead = rec["cast"]["characters"][0]["id"]
    rows = [
        sample_row(
            scene_id=scene,
            char_ids=[lead],
            action="弹窗弹出",
            dialogue="CODEX王子：嫁给我。",
        )
    ]
    exc = _err(lambda: svc.put_storyboard(pid, "EP01", _write(rows), raw={"rows": rows}))
    assert exc.status_code == 422
    assert exc.code == NAMED_CAST_MISSING


def test_o5_off_does_not_emit_or_block_g2(svc):
    object.__setattr__(svc.settings, "named_cast_check", "off")
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    scene = rec["cast"]["scenes"][0]["id"]
    lead = rec["cast"]["characters"][0]["id"]
    rows = [
        sample_row(
            scene_id=scene,
            char_ids=[lead],
            action="弹窗弹出",
            dialogue="CODEX王子：嫁给我。",
        )
    ]
    env = svc.put_storyboard(pid, "EP01", _write(rows), raw={"rows": rows})
    assert not any(str(w.get("code") or "").startswith("named_cast_") for w in env.get("validate_warnings") or [])
    val = svc.validate_storyboard(pid, "EP01")
    assert val["valid"] is True
    assert not blocking_named_cast_issues(val["issues"])
    gate = svc.confirm_gate_g2(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    assert gate["gate"]["locked"] is True


def test_sidecar_then_put_wires_and_g2_can_pass(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    outline_body = rec["outline"]["body_md"]
    scene = rec["cast"]["scenes"][0]["id"]
    lead = rec["cast"]["characters"][0]["id"]
    svc.sidecar_add_character(
        pid, "EP01", SidecarAddCharacterRequest(name="CODEX王子"), raw={"name": "CODEX王子"}
    )
    rec = svc._rec(pid, "EP01")
    prince = next(c for c in rec["cast"]["characters"] if c["name"] == "CODEX王子")
    rows = [
        sample_row(
            scene_id=scene,
            char_ids=[lead, prince["id"]],
            action="弹窗弹出",
            dialogue="CODEX王子：嫁给我。",
        )
    ]
    svc.put_storyboard(pid, "EP01", _write(rows), raw={"rows": rows})
    val = svc.validate_storyboard(pid, "EP01")
    assert blocking_named_cast_issues(val["issues"]) == []
    gate = svc.confirm_gate_g2(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    assert gate["gate"]["locked"] is True
    assert svc._rec(pid, "EP01")["outline"]["body_md"] == outline_body


def _preattached_frog_cast() -> dict:
    return {
        "characters": [
            {"id": "CHAR-01", "name": "林晚", "one_line": "女主", "library_ref": "CHAR-01"},
            {
                "id": "CHAR-02",
                "name": "奶蛙公主",
                "one_line": "预挂配角",
                "library_ref": "CHAR-02",
            },
            {"id": "CHAR-03", "name": "豆包", "one_line": "助手", "library_ref": "CHAR-03"},
            {"id": "CHAR-04", "name": "GPT王子", "one_line": "弹窗王子", "library_ref": "CHAR-04"},
        ],
        "scenes": [{"id": "SCENE-01"}],
        "version": 4,
        "locked": True,
    }


def test_preattached_generic_title_stays_on_id_after_prune():
    """Exact preattached 奶蛙公主 is B-GEN but must stay on CHAR-02 after prune."""
    cast = _preattached_frog_cast()
    frog = next(c for c in cast["characters"] if c["id"] == "CHAR-02")
    assert frog["name"] == "奶蛙公主"
    one_line = frog["one_line"]
    pool = ["林晚", "奶蛙公主", "豆包", "GPT王子"]
    assert resolve_hit_names("奶蛙公主", pool) == ["奶蛙公主"]
    assert resolve_to_pool_name("奶蛙公主", pool) == "奶蛙公主"
    rows = [
        sample_row(
            shot_id="S01",
            scene_id="SCENE-01",
            char_ids=["NONE"],
            action="奶蛙公主抬手示意",
            dialogue="奶蛙公主：跟我走。",
        )
    ]
    wired = apply_char_id_wiring(rows, {c["name"]: c["id"] for c in cast["characters"]})
    assert "CHAR-02" in wired[0]["char_ids"]
    pruned = prune_dirty_char_ids(wired, cast)
    assert "CHAR-02" in pruned[0]["char_ids"]
    assert next(c["name"] for c in cast["characters"] if c["id"] == "CHAR-02") == "奶蛙公主"
    assert next(c["one_line"] for c in cast["characters"] if c["id"] == "CHAR-02") == one_line


def test_modifier_phrases_fold_onto_preattached_and_do_not_open_ids():
    """圆身奶蛙公主 / 围攻奶蛙公主 stay on CHAR-02; no CHAR-07/08."""
    rec = {
        "outline": {
            "body_md": "1. 开钩\n黄色圆身奶蛙公主跳下台阶\n围攻奶蛙公主的侍卫散开\n"
        },
        "cast": _preattached_frog_cast(),
        "gate": {"locked": True, "last_decision": "pass"},
    }
    outline_body = rec["outline"]["body_md"]
    n = {"i": 4}

    def alloc(_rec):
        n["i"] += 1
        return f"CHAR-{n['i']:02d}"

    rows = [
        sample_row(
            shot_id="S01",
            scene_id="SCENE-01",
            char_ids=["NONE"],
            action="奶蛙公主抬手",
            dialogue=None,
        ),
        sample_row(
            shot_id="S02",
            seq=2,
            scene_id="SCENE-01",
            char_ids=["NONE"],
            action="黄色圆身奶蛙公主跳下台阶",
            dialogue=None,
        ),
        sample_row(
            shot_id="S03",
            seq=3,
            scene_id="SCENE-01",
            char_ids=["NONE"],
            action="围攻奶蛙公主的侍卫散开",
            dialogue=None,
        ),
    ]
    out, added = auto_merge_named_cast(rec, rows, alloc_char=alloc)
    names = [c["name"] for c in rec["cast"]["characters"]]
    ids = {c["id"] for c in rec["cast"]["characters"]}
    frog = next(c for c in rec["cast"]["characters"] if c["id"] == "CHAR-02")
    assert frog["name"] == "奶蛙公主"
    assert frog["one_line"] == "预挂配角"
    assert "圆身奶蛙公主" not in names
    assert "围攻奶蛙公主" not in names
    assert "CHAR-07" not in ids and "CHAR-08" not in ids
    assert added == []
    wired = {r["shot_id"]: r for r in out}
    assert "CHAR-02" in wired["S01"]["char_ids"]
    assert "CHAR-02" in wired["S02"]["char_ids"]
    assert "CHAR-02" in wired["S03"]["char_ids"]
    assert rec["outline"]["body_md"] == outline_body


def test_name_that_only_contains_frog_stem_does_not_bind_char02():
    """奶蛙脸 / 奶蛙卫 contain 奶蛙 but are not 奶蛙公主 — stay off CHAR-02."""
    cast = _preattached_frog_cast()
    pool = [c["name"] for c in cast["characters"]]
    assert resolve_to_pool_name("奶蛙脸", pool) != "奶蛙公主"
    assert "奶蛙公主" not in resolve_hit_names("奶蛙脸", pool)
    assert resolve_to_pool_name("奶蛙卫", pool) != "奶蛙公主"
    rec = {
        "outline": {"body_md": "1. 开钩\n奶蛙脸特写，石中奶蛙卫走过\n"},
        "cast": cast,
        "gate": {"locked": True, "last_decision": "pass"},
    }
    n = {"i": 4}

    def alloc(_rec):
        n["i"] += 1
        return f"CHAR-{n['i']:02d}"

    rows = [
        sample_row(
            shot_id="S04",
            scene_id="SCENE-01",
            char_ids=["CHAR-01"],
            action="奶蛙脸特写，石中奶蛙卫走过",
            dialogue=None,
        )
    ]
    out, added = auto_merge_named_cast(rec, rows, alloc_char=alloc)
    frog = next(c for c in rec["cast"]["characters"] if c["id"] == "CHAR-02")
    assert frog["name"] == "奶蛙公主"
    assert "CHAR-02" not in out[0]["char_ids"]
    names = [c["name"] for c in rec["cast"]["characters"]]
    assert "奶蛙脸" not in names
    assert "奶蛙卫" not in names
    assert added == []


def test_named_cast_issue_shape_uses_named_cast_prefix():
    issues = collect_issues(
        [
            sample_row(
                scene_id="SCENE-01",
                char_ids=["CHAR-01"],
                dialogue="CODEX王子：嫁给我。",
                action="弹窗",
            )
        ],
        shot_cap=12,
        tool_profile=None,
        cast={"characters": [{"id": "CHAR-01", "name": "林晚"}], "scenes": [{"id": "SCENE-01"}]},
        named_cast_check="warn",
    )
    named = [i for i in issues if str(i["code"]).startswith("named_cast_")]
    assert named
    assert all(i["severity"] == "warn" for i in named)
    assert issue("warn", NAMED_CAST_MISSING, "x")["code"].startswith("named_cast_")
