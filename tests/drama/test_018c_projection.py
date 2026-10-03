"""018c episode.json projection + FE-D1 hint versions. ForcePass=never. docs≠PASS."""

from __future__ import annotations

import json
from pathlib import Path

from aiv_drama.models import SidecarAddCharacterRequest
from aiv_drama_n2.models import StoryboardGenerateRequest

from tests.drama.helpers import generate_ready, lock_g1b, seed_project_episode


def _episode_json(data_dir, pid, ep="EP01") -> dict:
    path = Path(data_dir) / "projects" / pid / "episodes" / ep / ".aiv" / "episode.json"
    assert path.is_file(), path
    return json.loads(path.read_text(encoding="utf-8"))


def test_t_e1_confirm_outline_projects_intent(svc, data_dir):
    pid = seed_project_episode(svc)
    generate_ready(svc, pid)
    meta = _episode_json(data_dir, pid)
    assert meta["pipeline_profile"] == "drama"
    assert meta["intent"]["confirmed"] is True
    assert meta["intent"]["fingerprint"]
    assert meta["versions"]["outline"] >= 1
    assert meta["versions"]["cast"] >= 1
    assert "g1b" in meta["gates"]
    assert meta.get("projection_dirty") is False
    assert "force_pass" not in json.dumps(meta)


def test_t_e2_storyboard_meta_shot_cap_no_shot_budget(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    env = svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    assert env["storyboard"]["shot_cap"]
    assert env.get("skill_paths")
    meta = _episode_json(data_dir, pid)
    assert meta["intent"]["confirmed"] is True
    assert meta["versions"]["storyboard"] >= 1
    assert "g2" in meta["gates"]
    sbm = meta["storyboard_meta"]
    assert "shot_cap" in sbm
    assert "shot_budget" not in sbm
    assert sbm.get("skill_paths")
    assert ".skill/" in json.dumps(sbm["skill_paths"])
    assert "/home/" not in json.dumps(sbm)


def test_t_e3_projection_failure_api_still_ok(svc, monkeypatch):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr("aiv_drama.service.write_episode_json", boom)
    env = svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    assert env["ok"] is True
    assert env.get("projection_dirty") is True
    rec = svc._rec(pid, "EP01")
    assert rec["projection_dirty"] is True
    assert rec["storyboard"]["rows"]


def test_t_e4_sidecar_hint_has_version_numbers(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    old = rec["cast"]["version"]
    env = svc.sidecar_add_character(
        pid,
        "EP01",
        SidecarAddCharacterRequest(name="预挂丙将军", one_line="侧车配角"),
        raw={"name": "预挂丙将军"},
    )
    assert env["cast_changed"] is True
    hint = (env.get("hints") or [None])[0]
    assert hint["cast_version_old"] == old
    assert hint["cast_version_new"] == old + 1
    assert hint["g1b_still_locked"] is True
