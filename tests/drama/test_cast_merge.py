"""FIX-DN1 P0-1: same-name fold, used_names read, soft-suppress parallel leads."""

from __future__ import annotations

from aiv_drama.models import (
    AttachRequest,
    DramaBriefWrite,
    EpisodeCreate,
    GeneratedDraft,
    LibraryCharacterWrite,
    OutlineGenerateRequest,
    ProjectCreate,
)
from aiv_drama.service import DramaService

from tests.drama.helpers import generate_ready, persist_and_confirm_intent, seed_project_episode


def _draft(
    characters: list[dict],
    *,
    scenes: list[dict] | None = None,
    body_md: str = "# 大纲\n- 桥段序列：\n  1. 开篇钩子\n",
    lane: str = "female",
) -> GeneratedDraft:
    return GeneratedDraft(
        body_md=body_md,
        lane=lane,  # type: ignore[arg-type]
        shot_cap=12,
        characters=characters,
        scenes=scenes or [{"name": "办公室", "one_line": "开场"}],
        source_skills=[],
    )


def _seed_programmer_doubao(svc: DramaService, *, lane: str = "female") -> str:
    pid = svc.create_project(ProjectCreate(name="dn1-merge"))["project"]["id"]
    svc.put_library_character(
        pid, "CHAR-01", LibraryCharacterWrite(name="程序员", one_line="程序员·男", version=1)
    )
    svc.put_library_character(
        pid, "CHAR-02", LibraryCharacterWrite(name="豆包", one_line="奶蛙豆包", version=1)
    )
    svc.create_episode(pid, EpisodeCreate(episode_id="EP01", pipeline_profile="drama"))
    svc.put_brief(
        pid,
        "EP01",
        DramaBriefWrite(
            title_intent="程序员与两王子和豆包",
            lane_preference=lane,  # type: ignore[arg-type]
            hero_one_line="程序员·男",
        ),
    )
    svc.attach_character(pid, "EP01", AttachRequest(character_id="CHAR-01", version=1))
    svc.attach_character(pid, "EP01", AttachRequest(character_id="CHAR-02", version=1))
    return pid


def test_merge_folds_same_name_onto_preattach_keeps_ref(svc):
    pid = _seed_programmer_doubao(svc)
    rec = svc._rec(pid, "EP01")
    cast = svc._merge_generated_cast(
        rec,
        _draft(
            [
                {"name": "程序员", "one_line": "被模型改写的程序员"},
                {"name": "豆包", "one_line": "第二豆包"},
                {"name": "豆包", "one_line": "第三豆包"},
            ]
        ),
        pid,
    )
    names = [c["name"] for c in cast["characters"]]
    assert names.count("程序员") == 1
    assert names.count("豆包") == 1
    programmer = next(c for c in cast["characters"] if c["name"] == "程序员")
    doubao = next(c for c in cast["characters"] if c["name"] == "豆包")
    assert programmer["id"] == "CHAR-01"
    assert doubao["id"] == "CHAR-02"
    assert programmer["library_ref"] == {"id": "CHAR-01", "version": 1}
    assert doubao["library_ref"] == {"id": "CHAR-02", "version": 1}
    # preattach one_line wins; generated rewrite must not clobber identity
    assert programmer["one_line"] == "程序员·男"
    assert doubao["one_line"] == "奶蛙豆包"


def test_merge_soft_suppresses_parallel_protagonist_no_422(svc):
    pid = _seed_programmer_doubao(svc)
    rec = svc._rec(pid, "EP01")
    warnings: list[str] = []
    cast = svc._merge_generated_cast(
        rec,
        _draft(
            [
                {"name": "林码", "one_line": "重生女主"},
                {"name": "豆包", "one_line": "第二豆包"},
                {"name": "大皇子", "one_line": "傲慢王子"},
            ]
        ),
        pid,
        warnings=warnings,
    )
    names = [c["name"] for c in cast["characters"]]
    assert "林码" not in names
    assert names.count("程序员") == 1
    assert names.count("豆包") == 1
    assert "大皇子" in names
    assert any("soft-suppressed parallel protagonist" in w for w in warnings)
    ids = [c["id"] for c in cast["characters"]]
    assert ids.count("CHAR-01") == 1
    assert ids.count("CHAR-02") == 1


def test_merge_used_names_dedups_generated_without_preattach(svc):
    pid = seed_project_episode(svc, with_library=False)
    rec = svc._rec(pid, "EP01")
    cast = svc._merge_generated_cast(
        rec,
        _draft(
            [
                {"name": "豆包", "one_line": "第一只"},
                {"name": " 豆包 ", "one_line": "第二只"},
            ]
        ),
        pid,
    )
    named = [c for c in cast["characters"] if c["name"].strip() == "豆包"]
    assert len(named) == 1
    assert named[0]["library_ref"] is None


def test_merge_library_rename_overwrites_stale_cast_name_and_one_line(svc):
    pid = _seed_programmer_doubao(svc)
    rec = svc._rec(pid, "EP01")
    stale = next(c for c in rec["cast"]["characters"] if c["id"] == "CHAR-02")
    stale["one_line"] = "奶蛙脸陪聊破局者"
    assert stale["name"] == "豆包"
    svc.put_library_character(
        pid,
        "CHAR-02",
        LibraryCharacterWrite(
            name="奶蛙公主",
            one_line="踢飞两大模型王子，带着程序员私奔",
            version=2,
        ),
    )
    warnings: list[str] = []
    cast = svc._merge_generated_cast(
        rec,
        _draft(
            [
                {"name": "程序员", "one_line": "被模型改写的程序员"},
                {"name": "豆包", "one_line": "奶蛙脸陪聊破局者"},
            ]
        ),
        pid,
        warnings=warnings,
    )
    names = [c["name"] for c in cast["characters"]]
    assert "豆包" not in names
    frog = next(c for c in cast["characters"] if c["id"] == "CHAR-02")
    assert frog["name"] == "奶蛙公主"
    assert frog["one_line"] == "踢飞两大模型王子，带着程序员私奔"
    assert frog["library_ref"] == {"id": "CHAR-02", "version": 1}
    assert any("folded generated name '豆包' onto CHAR-02" in w for w in warnings)


def test_resolve_preattached_uses_library_identity_after_rename(svc):
    pid = _seed_programmer_doubao(svc)
    rec = svc._rec(pid, "EP01")
    stale = next(c for c in rec["cast"]["characters"] if c["id"] == "CHAR-02")
    stale["one_line"] = "奶蛙脸陪聊破局者"
    svc.put_library_character(
        pid,
        "CHAR-02",
        LibraryCharacterWrite(
            name="奶蛙公主",
            one_line="踢飞两大模型王子，带着程序员私奔",
            version=2,
        ),
    )
    cards = svc._resolve_preattached_characters(pid, rec)
    frog = next(c for c in cards if c["id"] == "CHAR-02")
    assert frog["name"] == "奶蛙公主"
    assert frog["one_line"] == "踢飞两大模型王子，带着程序员私奔"


def test_generate_after_rename_does_not_stale_confirmed_intent(svc):
    pid = _seed_programmer_doubao(svc)
    persist_and_confirm_intent(svc, pid, follow_precast=True)
    rec = svc._rec(pid, "EP01")
    svc.put_library_character(
        pid,
        "CHAR-02",
        LibraryCharacterWrite(
            name="奶蛙公主",
            one_line="踢飞两大模型王子，带着程序员私奔",
            version=2,
        ),
    )
    lane = rec["brief"]["lane_preference"]
    env = svc.generate_outline(
        pid,
        "EP01",
        OutlineGenerateRequest(lane=lane, provider="fixture"),
        raw={"lane": lane, "provider": "fixture"},
    )
    assert env["ok"] is True
    names = [c["name"] for c in env["cast"]["characters"]]
    assert "豆包" not in names
    frog = next(c for c in env["cast"]["characters"] if c["id"] == "CHAR-02")
    assert frog["name"] == "奶蛙公主"
    assert frog["one_line"] == "踢飞两大模型王子，带着程序员私奔"


def test_fixture_generate_library_rename_reaches_episode_cast(svc):
    pid = _seed_programmer_doubao(svc)
    rec = svc._rec(pid, "EP01")
    next(c for c in rec["cast"]["characters"] if c["id"] == "CHAR-02")["one_line"] = "奶蛙脸陪聊破局者"
    svc.put_library_character(
        pid,
        "CHAR-02",
        LibraryCharacterWrite(
            name="奶蛙公主",
            one_line="踢飞两大模型王子，带着程序员私奔",
            version=2,
        ),
    )
    persist_and_confirm_intent(svc, pid, follow_precast=True)
    env = generate_ready(svc, pid, svc._rec(pid, "EP01")["brief"]["lane_preference"])
    names = [c["name"] for c in env["cast"]["characters"]]
    assert "豆包" not in names
    frog = next(c for c in env["cast"]["characters"] if c["id"] == "CHAR-02")
    assert frog["name"] == "奶蛙公主"
    assert frog["one_line"] == "踢飞两大模型王子，带着程序员私奔"
    assert "奶蛙公主" in env["outline"]["body_md"]
    assert env["ok"] is True


def test_merge_never_overwrites_library_ref(svc):
    pid = seed_project_episode(svc)
    svc.attach_character(pid, "EP01", AttachRequest(character_id="CHAR-01", version=3))
    rec = svc._rec(pid, "EP01")
    # plant a generated-looking sibling id so fold must not steal the ref
    rec["cast"]["characters"].append(
        {"id": "CHAR-99", "name": "林晚", "one_line": "假行", "library_ref": None}
    )
    cast = svc._merge_generated_cast(
        rec,
        _draft([{"name": "林晚", "one_line": "模型另写"}]),
        pid,
    )
    lin = [c for c in cast["characters"] if c["name"] == "林晚"]
    assert len(lin) == 1
    assert lin[0]["id"] == "CHAR-01"
    assert lin[0]["library_ref"] == {"id": "CHAR-01", "version": 3}


def test_generate_attach_programmer_doubao_cast_is_clean(svc):
    pid = _seed_programmer_doubao(svc)
    env = generate_ready(svc, pid, "female")
    names = [c["name"] for c in env["cast"]["characters"]]
    assert names.count("程序员") == 1
    assert names.count("豆包") == 1
    refs = {c["name"]: c.get("library_ref") for c in env["cast"]["characters"]}
    assert refs["程序员"] == {"id": "CHAR-01", "version": 1}
    assert refs["豆包"] == {"id": "CHAR-02", "version": 1}
    assert "程序员" in env["outline"]["body_md"]
    assert env["ok"] is True


def test_lane_l1_warning_not_422(svc):
    pid = _seed_programmer_doubao(svc, lane="female")
    persist_and_confirm_intent(svc, pid, follow_precast=True)
    env = svc.generate_outline(
        pid,
        "EP01",
        OutlineGenerateRequest(lane="female", provider="fixture"),
        raw={"lane": "female", "provider": "fixture"},
    )
    assert env["ok"] is True
    warnings = env.get("warnings") or []
    assert any("lane female may clash" in w and "CHAR-01" in w for w in warnings)
    # still a legal 0.1.0 success envelope
    assert env["node"] == "D-N1"
    assert env["outline"]["lane"] == "female"
