"""F3 · template_paths / prompt_paths only; skill_paths untouched."""

from __future__ import annotations

import json
from pathlib import Path

from aiv_drama_n3.models import N3MaterializeRequest
from aiv_drama_n3.templates import (
    KEEP_CHAR_TEMPLATES,
    KEEP_STORYBOARD_REF,
    SEEDANCE_PARAM_REF,
    thicken_skill_paths,
    n3_template_paths,
)

from tests.drama.helpers import lock_g2, seed_project_episode


def test_template_and_prompt_paths_keep_only(svc):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    env = svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    expected = set(n3_template_paths(svc.settings.repo_root))
    assert set(env["template_paths"]) == expected
    assert set(env["prompt_paths"]) == expected
    for rel in KEEP_CHAR_TEMPLATES + KEEP_STORYBOARD_REF:
        if (svc.settings.repo_root / rel).is_file():
            assert rel in env["template_paths"]
    assert SEEDANCE_PARAM_REF not in env["template_paths"]
    assert env["scene_template"]["status"] == "deferred"
    assert env["scene_template"]["path"] is None
    assert not any("场景卡" in p for p in env["template_paths"])


def test_prompt_not_written_into_n1_n2_skill_paths(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    n2 = svc.get_storyboard(pid, "EP01")
    skill_before = list(n2.get("skill_paths") or [])
    assert all(not str(p).startswith(".prompt/") for p in skill_before)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    n2_after = svc.get_storyboard(pid, "EP01")
    skill_after = list(n2_after.get("skill_paths") or [])
    assert skill_after == skill_before
    assert all(not str(p).startswith(".prompt/") for p in skill_after)
    ep_json = Path(data_dir) / "projects" / pid / "episodes" / "EP01" / ".aiv" / "episode.json"
    meta = json.loads(ep_json.read_text(encoding="utf-8"))
    sbm = meta.get("storyboard_meta") or {}
    assert all(not str(p).startswith(".prompt/") for p in (sbm.get("skill_paths") or []))
    n3m = meta.get("n3_meta") or {}
    assert n3m.get("template_paths")
    assert n3m.get("prompt_paths")
    assert all(str(p).startswith(".prompt/consistency/") for p in n3m["template_paths"])
    outline_env = svc.get_outline(pid, "EP01")
    assert all(not str(p).startswith(".prompt/") for p in (outline_env.get("skill_paths") or []))
    assert thicken_skill_paths(svc.settings.repo_root, include_bio_skill=False) == []
    bio = thicken_skill_paths(svc.settings.repo_root, include_bio_skill=True)
    assert all(not str(p).startswith(".prompt/") for p in bio)
    assert SEEDANCE_PARAM_REF not in bio
