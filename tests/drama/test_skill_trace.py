"""018b skill-trace: generate observability, sanitize, consistency. ForcePass=never."""

from __future__ import annotations

import json
import re
from pathlib import Path

from aiv_drama.config import SKILL_PATHS
from aiv_drama.models import OutlineGenerateRequest
from aiv_drama.skill_trace import (
    SKILL_EXCERPT_TEXT_LIMIT,
    STORYBOARD_KEEP_PATHS,
    assert_skill_consistency,
    contains_host_abs,
    default_whitelist,
    record_skill_paths,
    sanitize_export_path,
    sha256_text,
)
from aiv_drama_n2.models import StoryboardGenerateRequest
from aiv_drama_n2.validate import SEEDANCE_SKILL_PATH

from tests.drama.helpers import generate_ready, lock_g1b, seed_project_episode

HOST_ABS_NEEDLE = re.compile(r"/Users/|/home/|\\\\Users\\\\|Desktop/Project")


def _dump(payload) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _assert_no_host_abs(payload) -> None:
    blob = _dump(payload)
    assert not HOST_ABS_NEEDLE.search(blob)
    assert not contains_host_abs(blob)


def test_t_s1_outline_generate_records_paths_or_none(svc):
    pid = seed_project_episode(svc)
    env = generate_ready(svc, pid, "female")
    ol = env["outline"]
    assert ol.get("skill_trace") in {"recorded", "none"}
    if ol["skill_trace"] == "none":
        assert ol["skill_paths"] == []
        assert ol["skill_trace_reason"]
    else:
        assert len(ol["skill_paths"]) >= 1
        assert SKILL_PATHS["female"] in ol["skill_paths"]
        assert ol["source_skills"]
        assert ol["excerpts"]
        for item in ol["excerpts"]:
            assert item["path"] in ol["skill_paths"]
            assert item["hash"]
            assert item["chars"] >= 0
            if item.get("text") is not None:
                assert len(item["text"]) <= SKILL_EXCERPT_TEXT_LIMIT
        got = svc.get_outline(pid, "EP01")["outline"]
        assert got["skill_paths"] == ol["skill_paths"]
        assert got["skill_trace"] == "recorded"
    assert_skill_consistency(ol, flag_used=bool(ol.get("source_skills") or ol["skill_paths"]))
    _assert_no_host_abs(env)


def test_t_s2_storyboard_generate_records_dongman(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    env = svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    sb = env["storyboard"]
    assert sb["storyboard_skill"] == "borrowed_dongman"
    assert sb["skill_trace"] == "recorded"
    assert len(sb["skill_paths"]) >= 1
    assert STORYBOARD_KEEP_PATHS[0] in sb["skill_paths"]
    assert all(SEEDANCE_SKILL_PATH not in p for p in sb["skill_paths"])
    for item in sb["excerpts"]:
        assert item["path"] in sb["skill_paths"]
        assert item["hash"]
        if item.get("text") is not None:
            assert len(item["text"]) <= SKILL_EXCERPT_TEXT_LIMIT
    assert_skill_consistency(sb, flag_used=True)
    _assert_no_host_abs(env)
    got = svc.get_storyboard(pid, "EP01")["storyboard"]
    assert got["skill_paths"] == sb["skill_paths"]
    assert got["skill_trace"] == "recorded"


def test_t_s3_http_generate_json_has_no_home_abs(client):
    proj = client.post("/api/v0/projects", json={"name": "skill"}).json()["project"]
    pid = proj["id"]
    client.post(
        f"/api/v0/projects/{pid}/episodes",
        json={"episode_id": "EP01", "pipeline_profile": "drama"},
    )
    client.put(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/brief",
        json={"title_intent": "被流放的庶女在边关翻盘", "lane_preference": "female"},
    )
    ol = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/outline",
        json={"lane": "female", "provider": "fixture"},
    )
    assert ol.status_code == 200
    body = ol.json()
    assert body["outline"]["skill_trace"] in {"recorded", "none"}
    assert body["outline"]["skill_paths"] or body["outline"]["skill_trace"] == "none"
    _assert_no_host_abs(body)
    client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/gates/g1b/confirm",
        json={"decision": "pass", "actor": "yangzhou"},
    )
    sb = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/storyboard/generate",
        json={"provider": "fixture"},
    )
    assert sb.status_code == 200
    payload = sb.json()
    assert payload["storyboard"]["skill_trace"] in {"recorded", "none"}
    _assert_no_host_abs(payload)


def test_t_s4_borrowed_flag_forbids_silent_empty(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    empty = svc.get_storyboard(pid, "EP01")["storyboard"]
    assert empty["storyboard_skill"] == "borrowed_dongman"
    assert empty["skill_paths"] == []
    assert empty["skill_trace"] == "none"
    assert empty["skill_trace_reason"] == "not_generated"
    assert_skill_consistency(empty, flag_used=True)
    gen = svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    sb = gen["storyboard"]
    assert sb["storyboard_skill"] == "borrowed_dongman"
    assert sb["skill_paths"]
    assert sb["skill_trace"] == "recorded"


def test_t_s5_sanitize_drops_dirty_and_seedance(tmp_path):
    skill = tmp_path / ".skill" / "writing" / "女频短剧编剧"
    skill.mkdir(parents=True)
    rel = ".skill/writing/女频短剧编剧/SKILL.md"
    (skill / "SKILL.md").write_text("# 女频\n型判定\n", encoding="utf-8")
    wl = default_whitelist()
    assert sanitize_export_path(rel, repo_root=tmp_path, whitelist=wl) == rel
    assert sanitize_export_path(str(tmp_path / rel), repo_root=tmp_path, whitelist=wl) == rel
    assert sanitize_export_path(f"/Users/me/{rel}", repo_root=tmp_path, whitelist=wl) is None
    assert sanitize_export_path(f"/home/me/{rel}", repo_root=tmp_path, whitelist=wl) is None
    assert sanitize_export_path(f"~/{rel}", repo_root=tmp_path, whitelist=wl) is None
    assert sanitize_export_path(f"../{rel}", repo_root=tmp_path, whitelist=wl) is None
    assert sanitize_export_path("C:\\Users\\me\\SKILL.md", repo_root=tmp_path, whitelist=wl) is None
    seed = f"{SEEDANCE_SKILL_PATH}/SKILL.md"
    assert sanitize_export_path(seed, repo_root=tmp_path, whitelist=wl) is None
    trace = record_skill_paths(
        [f"/Users/me/{rel}", rel, seed, "../etc/passwd"],
        repo_root=tmp_path,
        whitelist=wl,
    )
    assert trace["skill_trace"] == "recorded"
    assert trace["skill_paths"] == [rel]
    assert all("/Users/" not in p and "/home/" not in p for p in trace["skill_paths"])
    _assert_no_host_abs(trace)


def test_t_s6_custom_storyboard_is_explicit_none(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    env = svc.generate_storyboard(
        pid,
        "EP01",
        StoryboardGenerateRequest(provider="fixture", storyboard_skill="custom"),
        raw={"provider": "fixture", "storyboard_skill": "custom"},
    )
    sb = env["storyboard"]
    assert sb["storyboard_skill"] == "custom"
    assert sb["skill_paths"] == []
    assert sb["skill_trace"] == "none"
    assert sb["skill_trace_reason"] == "custom_no_skill_injection"
    assert_skill_consistency(sb, flag_used=True)
    _assert_no_host_abs(env)


def test_reset_outline_is_explicit_none(svc):
    pid = seed_project_episode(svc)
    generate_ready(svc, pid)
    from aiv_drama.models import OutlineResetRequest

    env = svc.reset_outline(pid, "EP01", OutlineResetRequest())
    ol = env["outline"]
    assert ol["skill_trace"] == "none"
    assert ol["skill_paths"] == []
    assert ol["skill_trace_reason"] == "reset"
    assert ol["source_skills"] == []


def test_projection_carries_skill_fields_without_host_abs(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    ep_dir = Path(data_dir) / "projects" / pid / "episodes" / "EP01"
    md = (ep_dir / "EP01-大纲.md").read_text(encoding="utf-8")
    assert "skill_paths:" in md
    assert "skill_trace: recorded" in md
    assert SKILL_PATHS["female"] in md
    sb_md = (ep_dir / "EP01-分镜.md").read_text(encoding="utf-8")
    assert "skill_paths:" in sb_md
    assert STORYBOARD_KEEP_PATHS[0] in sb_md
    meta = json.loads((ep_dir / ".aiv" / "episode.json").read_text(encoding="utf-8"))
    assert meta["outline_meta"]["skill_paths"]
    assert meta["storyboard_meta"]["skill_paths"]
    assert meta["storyboard_meta"]["skill_trace"] == "recorded"
    blob = "".join(p.read_text(encoding="utf-8") for p in ep_dir.rglob("*") if p.is_file())
    assert not HOST_ABS_NEEDLE.search(blob)


def test_excerpt_hash_is_full_file_sha256(tmp_path):
    rel = ".skill/writing/动态漫-转分镜/SKILL.md"
    path = tmp_path / rel
    path.parent.mkdir(parents=True)
    body = "# 转分镜\n" + ("镜号 " * 200)
    path.write_text(body, encoding="utf-8")
    trace = record_skill_paths([rel], repo_root=tmp_path, whitelist=default_whitelist())
    assert trace["skill_trace"] == "recorded"
    item = trace["excerpts"][0]
    assert item["hash"] == sha256_text(body)
    assert item["chars"] == len(body)
    assert item["text"]
    assert len(item["text"]) <= SKILL_EXCERPT_TEXT_LIMIT
    assert len(item["text"]) < item["chars"]
    assert item["start"] == 0
    assert item["end"] == len(item["text"])


def test_openapi_version_stays_010_and_lists_skill_fields(client):
    n1 = client.get("/openapi/drama-n0n1.v0.yaml")
    n2 = client.get("/openapi/drama-n2.v0.yaml")
    assert n1.status_code == n2.status_code == 200
    assert "version: 0.1.0" in n1.text
    assert "version: 0.1.0" in n2.text
    assert "0.2.0" not in n1.text.split("info:", 1)[-1][:200]
    assert "skill_paths" in n1.text
    assert "skill_paths" in n2.text
    assert "SkillExcerpt" in n1.text
    assert "SkillExcerpt" in n2.text


def test_male_outline_paths_are_lane_whitelist(svc):
    pid = seed_project_episode(svc, lane="male", title="废物少爷边关翻盘")
    env = svc.generate_outline(
        pid,
        "EP01",
        OutlineGenerateRequest(lane="male", provider="fixture"),
        raw={"lane": "male", "provider": "fixture"},
    )
    ol = env["outline"]
    assert ol["skill_trace"] == "recorded"
    assert SKILL_PATHS["male"] in ol["skill_paths"]
    assert all(p.startswith(".skill/writing/男频短剧编剧/") for p in ol["skill_paths"])
    _assert_no_host_abs(env)
