"""BRIEF-AIV-017b · FREEZE O3 — duration floors + adsorb. docs≠PASS. ForcePass=never."""

from __future__ import annotations

import json

import pytest

from aiv_drama.errors import AppError
from aiv_drama_n2.duration import adsorb_duration_row, adsorb_storyboard_rows
from aiv_drama_n2.models import StoryboardGenerateRequest, StoryboardWrite
from aiv_drama_n2.provider.llm import LlmStoryboardProvider
from aiv_drama_n2.validate import collect_issues, ready_for_n4

from tests.drama.helpers import lock_g1b, sample_row, seed_project_episode
from tests.drama.test_n2_llm import _fake_ok, _sample_outline_cast, _settings, _write_dongman_skill


def _cast() -> dict:
    return {
        "characters": [{"id": "CHAR-01", "name": "林晚"}],
        "scenes": [{"id": "SCENE-01", "name": "边关营帐"}],
    }


def _issues(rows, tool_profile):
    return collect_issues(
        rows,
        shot_cap=12,
        tool_profile=tool_profile,
        cast=_cast(),
        outline_body="# 大纲\n- 桥段序列：\n  1. 开篇\n  2. 立规\n  3. 加压\n  4. 主爽\n",
    )


def _write(rows, **kw):
    return StoryboardWrite.model_validate({"rows": rows, **kw})


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


# CAM §6 dogfood rewrite (seedance_2)
CAM_SEEDANCE_REWRITE = [
    ("STATIC", 3, 5, "seedance:5"),
    ("PUSH", 2, 5, "seedance:5"),
    ("WHIP_PUSH", 2, 8, "seedance:8"),
    ("ORBIT", 3, 8, "seedance:8"),
    ("HANDHELD", 2, 8, "seedance:8"),
    ("PULL", 2, 5, "seedance:5"),
    ("STATIC", 2, 5, "seedance:5"),
    ("DOLLY_ZOOM", 3, 8, "seedance:8"),
    ("PUSH", 2, 5, "seedance:5"),
    ("PAN_H", 2, 5, "seedance:5"),
    ("TRACK", 2, 5, "seedance:5"),
    ("CRANE_UP", 3, 8, "seedance:8"),
]


@pytest.mark.parametrize("camera,src,want,bucket", CAM_SEEDANCE_REWRITE)
def test_adsorb_seedance_matches_cam_table(camera, src, want, bucket):
    got = adsorb_duration_row(camera, src, "seedance_2")
    assert got.duration_s == want
    assert got.tool_duration_bucket == bucket
    assert got.warns == []


def test_adsorb_unset_profile_is_o9_noop():
    got = adsorb_duration_row("WHIP_PUSH", 2, None)
    assert got.duration_s == 2
    assert got.tool_duration_bucket is None
    assert got.warns == []


def test_adsorb_other_profiles_and_clamp():
    assert adsorb_duration_row("WHIP_PUSH", 2, "kling").duration_s == 10
    assert adsorb_duration_row("WHIP_PUSH", 2, "kling").tool_duration_bucket == "kling:10"
    assert adsorb_duration_row("STATIC", 2, "hailuo").duration_s == 6
    assert adsorb_duration_row("STATIC", 2, "hailuo").tool_duration_bucket == "hailuo:6"
    veo = adsorb_duration_row("STATIC", 3, "veo")
    assert veo.duration_s == 8
    assert veo.tool_duration_bucket == "veo:8"
    clamped = adsorb_duration_row("WHIP_PUSH", 12, "veo")
    assert clamped.duration_s == 8
    assert any(w["code"] == "duration_floor_clamped" for w in clamped.warns)


def test_validate_unset_profile_allows_short_shots_o9():
    rows = [
        sample_row(shot_id="S01", seq=1, duration_s=2, camera="STATIC", tool_duration_bucket=None),
        sample_row(shot_id="S02", seq=2, duration_s=3, camera="WHIP_PUSH", tool_duration_bucket=None, bridge_id="B2"),
    ]
    issues = _issues(rows, None)
    assert not any(i["code"] == "duration_bucket_mismatch" for i in issues)
    assert any(i["code"] == "tool_profile_unset" and i["severity"] == "warn" for i in issues)
    assert all(i["severity"] != "error" or i["code"] != "duration_bucket_mismatch" for i in issues)
    assert ready_for_n4(None, issues) is False
    assert not any(i.get("severity") == "error" for i in issues)


def test_validate_selected_profile_hard_fails_short_and_below_floor():
    short = [sample_row(duration_s=2, camera="STATIC", tool_duration_bucket=None)]
    short_issues = _issues(short, "seedance_2")
    assert any(
        i["code"] == "duration_bucket_mismatch" and i["severity"] == "error" for i in short_issues
    )
    assert ready_for_n4("seedance_2", short_issues) is False

    whip_low = [
        sample_row(
            duration_s=5,
            camera="WHIP_PUSH",
            tool_duration_bucket="seedance:5",
            grid_strict=True,
        )
    ]
    whip_issues = _issues(whip_low, "seedance_2")
    floor = [i for i in whip_issues if i["code"] == "duration_bucket_mismatch"]
    assert floor
    assert any((i.get("details") or {}).get("reason") == "duration_below_camera_floor" for i in floor)
    assert ready_for_n4("seedance_2", whip_issues) is False


def test_validate_selected_legal_and_grid_strict_warn():
    rows = [
        sample_row(
            duration_s=8,
            camera="WHIP_PUSH",
            tool_duration_bucket="seedance:8",
            grid_strict=True,
        )
    ]
    issues = _issues(rows, "seedance_2")
    assert not any(i["severity"] == "error" and i["code"] == "duration_bucket_mismatch" for i in issues)
    assert any(i["code"] == "duration_floor_low_for_grid" and i["severity"] == "warn" for i in issues)
    assert ready_for_n4("seedance_2", issues) is True


def test_put_unset_then_select_profile_re_adsorbs(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    scene = rec["cast"]["scenes"][0]["id"]
    short_rows = [
        sample_row(
            shot_id="S01",
            seq=1,
            duration_s=2,
            camera="STATIC",
            scene_id=scene,
            tool_duration_bucket=None,
        ),
        sample_row(
            shot_id="S02",
            seq=2,
            duration_s=3,
            camera="WHIP_PUSH",
            scene_id=scene,
            bridge_id="B2",
            tool_duration_bucket=None,
            grid_strict=True,
        ),
        sample_row(
            shot_id="S03",
            seq=3,
            duration_s=3,
            camera="CRANE_UP",
            scene_id=scene,
            bridge_id="B3",
            tool_duration_bucket=None,
        ),
    ]
    first = svc.put_storyboard(pid, "EP01", _write(short_rows), raw={"rows": short_rows})
    assert first["storyboard"]["tool_profile"] is None
    val = svc.validate_storyboard(pid, "EP01")
    assert val["valid"] is True
    assert val["ready_for_n4"] is False
    assert any(i["code"] == "tool_profile_unset" for i in val["issues"])
    assert not any(i["code"] == "duration_bucket_mismatch" for i in val["issues"])

    env = svc.put_storyboard(
        pid,
        "EP01",
        _write(short_rows, tool_profile="seedance_2"),
        raw={"rows": short_rows, "tool_profile": "seedance_2"},
    )
    rows = env["storyboard"]["rows"]
    assert env["storyboard"]["tool_profile"] == "seedance_2"
    assert rows[0]["duration_s"] == 5 and rows[0]["tool_duration_bucket"] == "seedance:5"
    assert rows[1]["duration_s"] == 8 and rows[1]["tool_duration_bucket"] == "seedance:8"
    assert rows[2]["duration_s"] == 8 and rows[2]["tool_duration_bucket"] == "seedance:8"
    after = svc.validate_storyboard(pid, "EP01")
    assert after["valid"] is True
    assert after["ready_for_n4"] is True
    assert not any(i["code"] == "duration_bucket_mismatch" and i["severity"] == "error" for i in after["issues"])


def test_put_same_profile_short_shot_still_hard_fails(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    scene = rec["cast"]["scenes"][0]["id"]
    legal = [
        sample_row(
            duration_s=5,
            camera="STATIC",
            scene_id=scene,
            tool_duration_bucket="seedance:5",
        )
    ]
    svc.put_storyboard(
        pid,
        "EP01",
        _write(legal, tool_profile="seedance_2"),
        raw={"rows": legal, "tool_profile": "seedance_2"},
    )
    short = [
        sample_row(
            duration_s=2,
            camera="STATIC",
            scene_id=scene,
            tool_duration_bucket=None,
        )
    ]
    exc = _err(
        lambda: svc.put_storyboard(
            pid,
            "EP01",
            _write(short, tool_profile="seedance_2"),
            raw={"rows": short, "tool_profile": "seedance_2"},
        )
    )
    assert exc.status_code == 422
    assert exc.code == "duration_bucket_mismatch"


def test_put_switch_profile_re_adsorbs_family(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    scene = rec["cast"]["scenes"][0]["id"]
    seedance = [
        sample_row(
            duration_s=8,
            camera="WHIP_PUSH",
            scene_id=scene,
            tool_duration_bucket="seedance:8",
            grid_strict=True,
        )
    ]
    svc.put_storyboard(
        pid,
        "EP01",
        _write(seedance, tool_profile="seedance_2"),
        raw={"rows": seedance, "tool_profile": "seedance_2"},
    )
    env = svc.put_storyboard(
        pid,
        "EP01",
        _write(seedance, tool_profile="kling"),
        raw={"rows": seedance, "tool_profile": "kling"},
    )
    row = env["storyboard"]["rows"][0]
    assert env["storyboard"]["tool_profile"] == "kling"
    assert row["duration_s"] == 10
    assert row["tool_duration_bucket"] == "kling:10"


def test_generate_with_profile_adsorbs_and_can_ready_n4(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    env = svc.generate_storyboard(
        pid,
        "EP01",
        StoryboardGenerateRequest(provider="fixture", tool_profile="seedance_2"),
        raw={"provider": "fixture", "tool_profile": "seedance_2"},
    )
    sb = env["storyboard"]
    assert sb["tool_profile"] == "seedance_2"
    assert all(r["duration_s"] in {5, 8, 10} for r in sb["rows"])
    assert all(r["tool_duration_bucket"] == f"seedance:{r['duration_s']}" for r in sb["rows"])
    val = svc.validate_storyboard(pid, "EP01")
    assert val["valid"] is True
    assert val["ready_for_n4"] is True


def test_llm_adsorbs_short_shots_when_profile_selected(tmp_path, monkeypatch):
    _write_dongman_skill(tmp_path)
    captured = _fake_ok(
        monkeypatch,
        rows=[
            {
                "bridge_id": "B1",
                "seq": 1,
                "duration_s": 2,
                "shot_size": "MS",
                "camera": "STATIC",
                "action": "推门入室",
                "char_ids": ["CHAR-01"],
                "scene_id": "SCENE-01",
                "tool_duration_bucket": "3s",
            },
            {
                "bridge_id": "B2",
                "seq": 2,
                "duration_s": 3,
                "shot_size": "CU",
                "camera": "WHIP_PUSH",
                "action": "急推翻盘",
                "char_ids": ["CHAR-01"],
                "scene_id": "SCENE-01",
                "tool_duration_bucket": "4s",
            },
        ],
    )
    outline, cast = _sample_outline_cast()
    rows = LlmStoryboardProvider(_settings(tmp_path)).generate(
        episode_id="EP01", outline=outline, cast=cast, shot_cap=12, tool_profile="seedance_2"
    )
    user = json.loads(captured["json"]["messages"][1]["content"])
    assert any("duration_s must be one of" in r for r in user["rules"])
    assert rows[0]["duration_s"] == 5 and rows[0]["tool_duration_bucket"] == "seedance:5"
    assert rows[1]["duration_s"] == 8 and rows[1]["tool_duration_bucket"] == "seedance:8"
    issues = collect_issues(
        rows, shot_cap=12, tool_profile="seedance_2", cast=cast, outline_body=outline["body_md"]
    )
    assert not any(i.get("code") == "duration_bucket_mismatch" and i.get("severity") == "error" for i in issues)


def test_adsorb_storyboard_skips_explicit_t_v3_contradiction():
    rows = [
        {
            "shot_id": "S01",
            "camera": "PUSH",
            "duration_s": 7,
            "tool_duration_bucket": "seedance:5",
        }
    ]
    out, _warns = adsorb_storyboard_rows(rows, "seedance_2", skip_explicit_contradiction=True)
    assert out[0]["duration_s"] == 7
    assert out[0]["tool_duration_bucket"] == "seedance:5"
