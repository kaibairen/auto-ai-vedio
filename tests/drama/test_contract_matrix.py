"""CONTRACT-BE §8 test matrix — D-N0 / D-N1 / G1b."""

from __future__ import annotations

from aiv_drama.errors import AppError
from aiv_drama.models import (
    AttachRequest,
    CastRowIn,
    CastWrite,
    DramaBriefWrite,
    EpisodeCreate,
    OutlineGenerateRequest,
    OutlineWrite,
    ProjectCreate,
)
from aiv_drama.validate import outline_has_beats

from tests.drama.helpers import generate_ready, seed_project_episode


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def test_t_b1_brief_empty(svc):
    pid = seed_project_episode(svc, title=None)
    exc = _err(lambda: svc.put_brief(pid, "EP01", DramaBriefWrite()))
    assert exc.status_code == 422
    assert exc.code == "brief_incomplete"


def test_t_b2_lane_unset_saves_brief(svc):
    pid = seed_project_episode(svc, title=None)
    env = svc.put_brief(
        pid,
        "EP01",
        DramaBriefWrite(title_intent="只一句话", lane_preference="unset"),
    )
    assert env["ok"] is True
    assert env["node"] == "D-N0"
    assert env["brief"]["lane_preference"] == "unset"
    assert env["brief"]["version"] == 1


def test_t_o1_unset_generate_lane_required(svc):
    pid = seed_project_episode(svc, lane="unset")
    exc = _err(
        lambda: svc.generate_outline(pid, "EP01", OutlineGenerateRequest(provider="fixture"), raw={"provider": "fixture"})
    )
    assert exc.status_code == 422
    assert exc.code == "lane_required"


def test_t_o2_female_fixture(svc):
    pid = seed_project_episode(svc, lane="unset")
    env = generate_ready(svc, pid, "female")
    assert env["ok"] is True
    assert env["node"] == "D-N1"
    ol = env["outline"]
    assert ol["lane"] == "female"
    assert ol["shot_cap"] == 12
    assert outline_has_beats(ol["body_md"])
    assert "宫格" not in ol["body_md"]
    assert env["cast"]["characters"]
    assert env["cast"]["scenes"]


def test_t_o3_outline_contains_prompts(svc):
    pid = seed_project_episode(svc)
    generate_ready(svc, pid)
    exc = _err(
        lambda: svc.put_outline(
            pid,
            "EP01",
            OutlineWrite(body_md="# x\n- 桥段序列：\n  1. 有桥段\n使用九宫格出片\n宫格指令\n"),
        )
    )
    assert exc.status_code == 422
    assert exc.code == "outline_contains_prompts"


def test_t_c1_attach_then_generate_keeps_ref(svc):
    pid = seed_project_episode(svc)
    svc.attach_character(pid, "EP01", AttachRequest(character_id="CHAR-01", version=3))
    env = generate_ready(svc, pid)
    refs = [c.get("library_ref") for c in env["cast"]["characters"]]
    assert {"id": "CHAR-01", "version": 3} in refs
    lin = [c for c in env["cast"]["characters"] if c["name"] == "林晚"]
    assert len(lin) == 1
    assert lin[0]["id"] == "CHAR-01"
    assert lin[0]["library_ref"] == {"id": "CHAR-01", "version": 3}


def test_t_c2_fe_invented_char_id(svc):
    pid = seed_project_episode(svc)
    generate_ready(svc, pid)
    exc = _err(
        lambda: svc.put_cast(
            pid,
            "EP01",
            CastWrite(
                characters=[CastRowIn(id="CHAR-99", name="假", one_line="前端自造")],
                scenes=[CastRowIn(name="场", one_line="一句话")],
            ),
        )
    )
    assert exc.status_code == 422
    assert exc.code == "validation"
    assert exc.details.get("id") == "CHAR-99"


def test_t_g1_empty_cast_pass(svc):
    pid = seed_project_episode(svc)
    generate_ready(svc, pid)
    rec = svc._rec(pid, "EP01")
    rec["cast"]["characters"] = []
    rec["cast"]["scenes"] = []
    exc = _err(lambda: svc.confirm_gate(pid, "EP01", {"decision": "pass", "actor": "yangzhou"}))
    assert exc.status_code == 422
    assert exc.code == "cast_incomplete"


def test_t_g2_pass_locked_next_edges_no_dn2_job(svc):
    pid = seed_project_episode(svc)
    generate_ready(svc, pid)
    env = svc.confirm_gate(pid, "EP01", {"decision": "pass", "actor": "yangzhou", "note": "ok"})
    assert env["gate"]["state"] == "passed"
    assert env["gate"]["locked"] is True
    assert env["outline"]["locked"] is True
    assert env["outline"]["confirmed_by"] == "yangzhou"
    assert env["cast"]["locked"] is True
    assert env["cast"]["confirmed_by"] == "yangzhou"
    assert env["next_edges"] == ["D-N2"]
    rec = svc._rec(pid, "EP01")
    assert rec["d_n2_jobs"] == []
    assert rec["episode"]["status"] == "locked_g1b"


def test_t_g3_force_pass_forbidden(svc):
    pid = seed_project_episode(svc)
    generate_ready(svc, pid)
    exc = _err(
        lambda: svc.confirm_gate(
            pid, "EP01", {"decision": "pass", "actor": "yangzhou", "force_pass": True}
        )
    )
    assert exc.status_code == 400
    assert exc.code == "force_pass_forbidden"


def test_t_g4_locked_put_without_unlock(svc):
    pid = seed_project_episode(svc)
    generate_ready(svc, pid)
    svc.confirm_gate(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    rec = svc._rec(pid, "EP01")
    ver = rec["outline"]["version"]
    exc = _err(
        lambda: svc.put_outline(
            pid,
            "EP01",
            OutlineWrite(body_md=rec["outline"]["body_md"] + "\n- 补一句\n", unlock_edit=False),
        )
    )
    assert exc.status_code == 409
    assert exc.code == "locked"
    assert svc._rec(pid, "EP01")["outline"]["version"] == ver


def test_t_g5_unlock_edit(svc):
    pid = seed_project_episode(svc)
    generate_ready(svc, pid)
    svc.confirm_gate(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    rec = svc._rec(pid, "EP01")
    ver = rec["outline"]["version"]
    body = rec["outline"]["body_md"]
    env = svc.put_outline(
        pid,
        "EP01",
        OutlineWrite(body_md=body.replace("集尾悬念", "集尾悬念（改稿）"), unlock_edit=True),
    )
    assert env["outline"]["locked"] is False
    assert env["outline"]["version"] == ver + 1
    assert env["outline"]["confirmed_by"] is None
    stale = svc._rec(pid, "EP01")["episode"]["stale_downstream"]
    assert "D-N2" in stale
    assert env["next_edges"] == []


def test_t_g6_reject_stays_editable(svc):
    pid = seed_project_episode(svc)
    generate_ready(svc, pid)
    env = svc.confirm_gate(pid, "EP01", {"decision": "reject", "actor": "yangzhou", "note": "中段空"})
    assert env["gate"]["state"] == "rejected"
    assert env["gate"]["locked"] is False
    assert env["outline"]["locked"] is False
    assert env["outline"]["confirmed_by"] is None
    assert env["next_edges"] == []
    again = svc.put_outline(
        pid,
        "EP01",
        OutlineWrite(body_md=env["outline"]["body_md"] + "\n"),
    )
    assert again["outline"]["version"] >= 1


def test_t_d1_downstream_unlocked(svc):
    pid = seed_project_episode(svc)
    generate_ready(svc, pid)
    exc = _err(lambda: svc.get_downstream(pid, "EP01"))
    assert exc.status_code == 409
    assert exc.code == "upstream_unlocked"
    svc.confirm_gate(pid, "EP01", {"decision": "pass", "actor": "yangzhou"})
    down = svc.get_downstream(pid, "EP01")
    assert down["started"] is False
    assert down["jobs"] == []
    assert down["consumer"] == "D-N2"
    assert down["outline"]["locked"] is True


def test_t_v1_if_match(svc):
    pid = seed_project_episode(svc)
    generate_ready(svc, pid)
    rec = svc._rec(pid, "EP01")
    exc = _err(
        lambda: svc.put_outline(
            pid,
            "EP01",
            OutlineWrite(body_md=rec["outline"]["body_md"]),
            if_match="999",
        )
    )
    assert exc.status_code == 409
    assert exc.code == "version_conflict"


def test_t_l1_attach_character_from_other_library(svc):
    seed_project_episode(svc)
    pid_b = svc.create_project(ProjectCreate(name="B"))["project"]["id"]
    svc.create_episode(pid_b, EpisodeCreate(episode_id="EP01", pipeline_profile="drama"))
    svc.put_brief(pid_b, "EP01", DramaBriefWrite(title_intent="另一集", lane_preference="female"))
    exc = _err(lambda: svc.attach_character(pid_b, "EP01", AttachRequest(character_id="CHAR-01", version=3)))
    assert exc.status_code == 404
    assert exc.code == "not_found"


def test_t_i1_idempotent_generate(svc):
    pid = seed_project_episode(svc)
    a = svc.generate_outline(
        pid,
        "EP01",
        OutlineGenerateRequest(lane="female", provider="fixture"),
        raw={"lane": "female"},
        idempotency_key="gen-1",
    )
    b = svc.generate_outline(
        pid,
        "EP01",
        OutlineGenerateRequest(lane="female", provider="fixture"),
        raw={"lane": "female"},
        idempotency_key="gen-1",
    )
    assert a["outline"]["version"] == b["outline"]["version"]
    assert a["outline"]["body_md"] == b["outline"]["body_md"]
