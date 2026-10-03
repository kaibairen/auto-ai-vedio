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


def _seed_preattached_pair(svc: DramaService, *, lane: str = "female") -> str:
    pid = svc.create_project(ProjectCreate(name="dn1-merge"))["project"]["id"]
    svc.put_library_character(
        pid, "CHAR-01", LibraryCharacterWrite(name="预挂甲", one_line="预挂甲·男", version=1)
    )
    svc.put_library_character(
        pid, "CHAR-02", LibraryCharacterWrite(name="预挂乙", one_line="预挂乙·配", version=1)
    )
    svc.create_episode(pid, EpisodeCreate(episode_id="EP01", pipeline_profile="drama"))
    svc.put_brief(
        pid,
        "EP01",
        DramaBriefWrite(
            title_intent="预挂甲与预挂乙",
            lane_preference=lane,  # type: ignore[arg-type]
            hero_one_line="预挂甲·男",
        ),
    )
    svc.attach_character(pid, "EP01", AttachRequest(character_id="CHAR-01", version=1))
    svc.attach_character(pid, "EP01", AttachRequest(character_id="CHAR-02", version=1))
    return pid


def test_merge_folds_same_name_onto_preattach_keeps_ref(svc):
    pid = _seed_preattached_pair(svc)
    rec = svc._rec(pid, "EP01")
    cast = svc._merge_generated_cast(
        rec,
        _draft(
            [
                {"name": "预挂甲", "one_line": "被模型改写的预挂甲"},
                {"name": "预挂乙", "one_line": "第二预挂乙"},
                {"name": "预挂乙", "one_line": "第三预挂乙"},
            ]
        ),
        pid,
    )
    names = [c["name"] for c in cast["characters"]]
    assert names.count("预挂甲") == 1
    assert names.count("预挂乙") == 1
    lead = next(c for c in cast["characters"] if c["name"] == "预挂甲")
    support = next(c for c in cast["characters"] if c["name"] == "预挂乙")
    assert lead["id"] == "CHAR-01"
    assert support["id"] == "CHAR-02"
    assert lead["library_ref"] == {"id": "CHAR-01", "version": 1}
    assert support["library_ref"] == {"id": "CHAR-02", "version": 1}
    assert lead["one_line"] == "预挂甲·男"
    assert support["one_line"] == "预挂乙·配"


def test_merge_folds_prefix_and_suffix_onto_preattach(svc):
    pid = _seed_preattached_pair(svc)
    rec = svc._rec(pid, "EP01")
    cast = svc._merge_generated_cast(
        rec,
        _draft(
            [
                {"name": "小预挂甲", "one_line": "前缀包装"},
                {"name": "预挂乙大人", "one_line": "后缀包装"},
                {"name": "预挂戊", "one_line": "漏库新角色"},
            ]
        ),
        pid,
    )
    names = [c["name"] for c in cast["characters"]]
    assert names.count("预挂甲") == 1
    assert names.count("预挂乙") == 1
    assert "小预挂甲" not in names
    assert "预挂乙大人" not in names
    assert "预挂戊" in names
    assert next(c for c in cast["characters"] if c["name"] == "预挂甲")["id"] == "CHAR-01"
    assert next(c for c in cast["characters"] if c["name"] == "预挂乙")["id"] == "CHAR-02"


def test_merge_soft_suppresses_parallel_protagonist_no_422(svc):
    pid = _seed_preattached_pair(svc)
    rec = svc._rec(pid, "EP01")
    warnings: list[str] = []
    cast = svc._merge_generated_cast(
        rec,
        _draft(
            [
                {"name": "另造甲", "one_line": "重生女主"},
                {"name": "预挂乙", "one_line": "第二预挂乙"},
                {"name": "预挂戊", "one_line": "漏库新角色"},
            ]
        ),
        pid,
        warnings=warnings,
    )
    names = [c["name"] for c in cast["characters"]]
    assert "另造甲" not in names
    assert names.count("预挂甲") == 1
    assert names.count("预挂乙") == 1
    assert "预挂戊" in names
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
                {"name": "预挂乙", "one_line": "第一只"},
                {"name": " 预挂乙 ", "one_line": "第二只"},
            ]
        ),
        pid,
    )
    named = [c for c in cast["characters"] if c["name"].strip() == "预挂乙"]
    assert len(named) == 1
    assert named[0]["library_ref"] is None


def test_merge_never_overwrites_library_ref(svc):
    pid = seed_project_episode(svc)
    svc.attach_character(pid, "EP01", AttachRequest(character_id="CHAR-01", version=3))
    rec = svc._rec(pid, "EP01")
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


def test_generate_attach_preattached_pair_cast_is_clean(svc):
    pid = _seed_preattached_pair(svc)
    env = generate_ready(svc, pid, "female")
    names = [c["name"] for c in env["cast"]["characters"]]
    assert names.count("预挂甲") == 1
    assert names.count("预挂乙") == 1
    refs = {c["name"]: c.get("library_ref") for c in env["cast"]["characters"]}
    assert refs["预挂甲"] == {"id": "CHAR-01", "version": 1}
    assert refs["预挂乙"] == {"id": "CHAR-02", "version": 1}
    assert "预挂甲" in env["outline"]["body_md"]
    assert env["ok"] is True


def test_lane_l1_warning_not_422(svc):
    pid = _seed_preattached_pair(svc, lane="female")
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
    assert env["node"] == "D-N1"
    assert env["outline"]["lane"] == "female"
