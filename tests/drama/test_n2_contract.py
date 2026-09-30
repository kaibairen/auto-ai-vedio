"""CONTRACT-BE §8 test matrix — D-N2 / G2. docs≠PASS. ForcePass=never."""

from __future__ import annotations

from aiv_drama.errors import AppError
from aiv_drama.models import OutlineWrite
from aiv_drama_n2.models import (
    StoryboardGenerateRequest,
    StoryboardReorderRequest,
    StoryboardResetRequest,
    StoryboardWrite,
)

from tests.drama.helpers import generate_ready, lock_g1b, sample_row, seed_project_episode


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def _write(rows, **kw):
    return StoryboardWrite.model_validate({"rows": rows, **kw})


def test_t_u1_generate_upstream_unlocked(svc):
    pid = seed_project_episode(svc)
    generate_ready(svc, pid)
    exc = _err(lambda: svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture")))
    assert exc.status_code == 409
    assert exc.code == "upstream_unlocked"
    assert exc.details.get("node") == "D-N1"
    assert exc.details.get("gate") == "g1b"


def test_t_u2_get_upstream_unlocked(svc):
    pid = seed_project_episode(svc)
    generate_ready(svc, pid)
    exc = _err(lambda: svc.get_storyboard(pid, "EP01"))
    assert exc.status_code == 409
    assert exc.code == "upstream_unlocked"


def test_t_g1_generate_fixture_inherits_shot_cap(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    empty = svc.get_storyboard(pid, "EP01")
    assert empty["storyboard"]["version"] == 0
    assert empty["storyboard"]["rows"] == []
    env = svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    assert env["ok"] is True
    assert env["node"] == "D-N2"
    sb = env["storyboard"]
    assert sb["shot_cap"] == 12
    assert 1 <= sb["shot_count"] <= 12
    assert sb["storyboard_skill"] == "borrowed_dongman"
    assert sb["locked"] is False
    assert sb["ready_for_n4"] is False
    assert all(r.get("bridge_id") for r in sb["rows"])
    assert all(r["shot_size"] in {"ELS", "LS", "MS", "CU", "ECU"} for r in sb["rows"])


def test_t_g2_thirteen_rows_shot_cap_exceeded(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    scene = rec["cast"]["scenes"][0]["id"]
    rows = [
        sample_row(shot_id=f"S{i:02d}", seq=i, bridge_id="B1", scene_id=scene)
        for i in range(1, 14)
    ]
    exc = _err(lambda: svc.put_storyboard(pid, "EP01", _write(rows), raw={"rows": rows}))
    assert exc.status_code == 422
    assert exc.code == "shot_cap_exceeded"


def test_t_v1_chinese_shot_size(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    scene = rec["cast"]["scenes"][0]["id"]
    rows = [sample_row(shot_size="中景", scene_id=scene)]
    exc = _err(lambda: svc.put_storyboard(pid, "EP01", _write(rows), raw={"rows": rows}))
    assert exc.status_code == 422
    assert exc.code == "cam_enum_invalid"


def test_t_v2_stacked_camera(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    scene = rec["cast"]["scenes"][0]["id"]
    rows = [sample_row(camera="PUSH+ORBIT", scene_id=scene)]
    exc = _err(lambda: svc.put_storyboard(pid, "EP01", _write(rows), raw={"rows": rows}))
    assert exc.status_code == 422
    assert exc.code == "cam_enum_invalid"


def test_t_v3_duration_bucket_mismatch(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    scene = rec["cast"]["scenes"][0]["id"]
    rows = [sample_row(duration_s=7, tool_duration_bucket="seedance:5", scene_id=scene)]
    exc = _err(
        lambda: svc.put_storyboard(
            pid, "EP01", _write(rows, tool_profile="seedance_2"), raw={"rows": rows, "tool_profile": "seedance_2"}
        )
    )
    assert exc.status_code == 422
    assert exc.code == "duration_bucket_mismatch"


def test_t_v4_no_tool_profile_g2_pass_not_ready_n4(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    env = svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    assert env["storyboard"]["tool_profile"] is None
    val = svc.validate_storyboard(pid, "EP01")
    assert val["valid"] is True
    assert val["ready_for_n4"] is False
    assert any(i["code"] == "tool_profile_unset" for i in val["issues"])
    gate = svc.confirm_gate_g2(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    assert gate["gate"]["locked"] is True
    assert gate["next_edges"] == ["D-N3"]
    assert gate["storyboard"]["ready_for_n4"] is False
    assert svc._rec(pid, "EP01")["d_n3_jobs"] == []


def test_t_v5_prompt_forbidden(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    scene = rec["cast"]["scenes"][0]["id"]
    rows = [sample_row(action="Seedance 0-5s:[Image1] 完整时间轴", scene_id=scene)]
    exc = _err(lambda: svc.put_storyboard(pid, "EP01", _write(rows), raw={"rows": rows}))
    assert exc.status_code == 422
    assert exc.code == "prompt_forbidden"


def test_t_v5b_prompt_column_forbidden(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    raw = {"rows": [sample_row()], "prompt": "do not store"}
    exc = _err(lambda: svc.put_storyboard(pid, "EP01", _write([sample_row()]), raw=raw))
    assert exc.status_code == 422
    assert exc.code == "prompt_forbidden"


def test_t_v6_unknown_char(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    scene = rec["cast"]["scenes"][0]["id"]
    rows = [sample_row(char_ids=["CHAR-99"], scene_id=scene)]
    exc = _err(lambda: svc.put_storyboard(pid, "EP01", _write(rows), raw={"rows": rows}))
    assert exc.status_code == 422
    assert exc.code == "cast_id_unknown"
    assert exc.details.get("id") == "CHAR-99"


def test_t_v7_none_chars_allowed(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    scene = rec["cast"]["scenes"][0]["id"]
    rows = [sample_row(char_ids=["NONE"], scene_id=scene, notes="空镜/群杂")]
    env = svc.put_storyboard(pid, "EP01", _write(rows), raw={"rows": rows})
    assert env["ok"] is True
    assert env["storyboard"]["rows"][0]["char_ids"] == ["NONE"]


def test_t_v8_bridge_id_missing(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    scene = rec["cast"]["scenes"][0]["id"]
    rows = [sample_row(bridge_id="   ", scene_id=scene)]
    exc = _err(lambda: svc.put_storyboard(pid, "EP01", _write(rows), raw={"rows": rows}))
    assert exc.status_code == 422
    assert exc.code == "bridge_id_missing"


def test_t_v9_els_ecu_jump_warn(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    rec = svc._rec(pid, "EP01")
    scene = rec["cast"]["scenes"][0]["id"]
    rows = [
        sample_row(shot_id="S01", seq=1, shot_size="ELS", camera="STATIC", scene_id=scene, transition=None),
        sample_row(shot_id="S02", seq=2, shot_size="ECU", camera="STATIC", scene_id=scene, transition=None, notes=None),
    ]
    env = svc.put_storyboard(pid, "EP01", _write(rows), raw={"rows": rows})
    codes = {w["code"] for w in env.get("validate_warnings") or []}
    assert "shot_size_jump_j2" in codes or "shot_size_jump_j1" in codes


def test_t_r1_reorder_unlocked(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    gen = svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    ids = [r["shot_id"] for r in gen["storyboard"]["rows"]]
    assert len(ids) >= 2
    flipped = list(reversed(ids))
    env = svc.reorder_storyboard(pid, "EP01", StoryboardReorderRequest(shot_ids=flipped))
    got = [r["shot_id"] for r in env["storyboard"]["rows"]]
    assert got == flipped
    assert [r["seq"] for r in env["storyboard"]["rows"]] == list(range(1, len(flipped) + 1))
    assert env["storyboard"]["rows"][0]["bridge_id"]


def test_t_r2_reorder_locked(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    gen = svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    svc.confirm_gate_g2(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    ids = [r["shot_id"] for r in gen["storyboard"]["rows"]]
    exc = _err(lambda: svc.reorder_storyboard(pid, "EP01", StoryboardReorderRequest(shot_ids=ids)))
    assert exc.status_code == 409
    assert exc.code == "locked"


def test_t_c1_confirm_pass_no_dn3_job(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    env = svc.confirm_gate_g2(pid, "EP01", {"decision": "pass", "actor": "yangzhou", "note": "ok"})
    assert env["gate"]["state"] == "passed"
    assert env["gate"]["locked"] is True
    assert env["storyboard"]["locked"] is True
    assert env["storyboard"]["confirmed_by"] == "yangzhou"
    assert env["next_edges"] == ["D-N3"]
    rec = svc._rec(pid, "EP01")
    assert rec["d_n3_jobs"] == []
    assert rec["episode"]["next_edges"] == ["D-N3"]


def test_t_c2_force_pass_forbidden(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    exc = _err(
        lambda: svc.confirm_gate_g2(
            pid, "EP01", {"decision": "pass", "actor": "yangzhou", "force_pass": True}
        )
    )
    assert exc.status_code == 400
    assert exc.code == "force_pass_forbidden"


def test_t_c3_confirm_empty(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    svc.reset_storyboard(pid, "EP01", StoryboardResetRequest())
    exc = _err(lambda: svc.confirm_gate_g2(pid, "EP01", {"decision": "pass", "actor": "yangzhou"}))
    assert exc.status_code == 422
    assert exc.code == "storyboard_empty"


def test_t_c4_stale_upstream_blocks_pass(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    rec = svc._rec(pid, "EP01")
    svc.put_outline(
        pid,
        "EP01",
        OutlineWrite(body_md=rec["outline"]["body_md"] + "\n", unlock_edit=True),
    )
    rec = svc._rec(pid, "EP01")
    assert rec["storyboard"]["stale"] is True
    # re-lock G1b so confirm reaches stale check
    svc.confirm_gate(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    exc = _err(lambda: svc.confirm_gate_g2(pid, "EP01", {"decision": "pass", "actor": "yangzhou"}))
    assert exc.status_code == 409
    assert exc.code == "stale_upstream"


def test_t_c5_reject_stays_editable(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    env = svc.confirm_gate_g2(pid, "EP01", {"decision": "reject", "actor": "yangzhou", "note": "G2-D3"})
    assert env["gate"]["state"] == "rejected"
    assert env["gate"]["locked"] is False
    assert env["storyboard"]["locked"] is False
    assert env["next_edges"] == ["D-N2"]
    rec = svc._rec(pid, "EP01")
    scene = rec["cast"]["scenes"][0]["id"]
    rows = [sample_row(scene_id=scene, action="改一镜")]
    again = svc.put_storyboard(pid, "EP01", _write(rows), raw={"rows": rows})
    assert again["storyboard"]["version"] >= 1


def test_t_l1_locked_put_without_unlock(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    svc.confirm_gate_g2(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    rec = svc._rec(pid, "EP01")
    ver = rec["storyboard"]["version"]
    scene = rec["cast"]["scenes"][0]["id"]
    rows = [sample_row(scene_id=scene)]
    exc = _err(lambda: svc.put_storyboard(pid, "EP01", _write(rows), raw={"rows": rows}))
    assert exc.status_code == 409
    assert exc.code == "locked"
    assert svc._rec(pid, "EP01")["storyboard"]["version"] == ver


def test_t_l2_unlock_edit(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    svc.confirm_gate_g2(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    rec = svc._rec(pid, "EP01")
    ver = rec["storyboard"]["version"]
    scene = rec["cast"]["scenes"][0]["id"]
    rows = [sample_row(scene_id=scene, action="解锁改表")]
    env = svc.put_storyboard(
        pid, "EP01", _write(rows, unlock_edit=True), raw={"rows": rows, "unlock_edit": True}
    )
    assert env["storyboard"]["locked"] is False
    assert env["storyboard"]["version"] == ver + 1
    assert env["storyboard"]["confirmed_by"] is None
    stale = svc._rec(pid, "EP01")["episode"]["stale_downstream"]
    assert "D-N3" in stale


def test_t_d1_dn3_consumer_unlocked(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    svc.generate_storyboard(pid, "EP01", StoryboardGenerateRequest(provider="fixture"))
    exc = _err(lambda: svc.get_dn3_consumer(pid, "EP01"))
    assert exc.status_code == 409
    assert exc.code == "upstream_unlocked"
    assert exc.details.get("node") == "D-N2"
    svc.confirm_gate_g2(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    down = svc.get_dn3_consumer(pid, "EP01")
    assert down["started"] is False
    assert down["jobs"] == []
    assert down["consumer"] == "D-N3"


def test_t_i1_idempotent_generate(svc):
    pid = seed_project_episode(svc)
    lock_g1b(svc, pid)
    a = svc.generate_storyboard(
        pid, "EP01", StoryboardGenerateRequest(provider="fixture"), idempotency_key="sb-1"
    )
    b = svc.generate_storyboard(
        pid, "EP01", StoryboardGenerateRequest(provider="fixture"), idempotency_key="sb-1"
    )
    assert a["storyboard"]["version"] == b["storyboard"]["version"]
    assert a["storyboard"]["rows"] == b["storyboard"]["rows"]
