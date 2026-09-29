from __future__ import annotations

from aiv_n1.errors import AppError
from aiv_n1.models import SessionCreate, StepSubmit


def test_t_a01_session_starts_at_a1_raw(service, project, ep):
    env = service.create_session(project, ep, SessionCreate(path="A", provider="fixture"))
    assert env["ok"] is True
    assert env["session"]["current_step"] == "a1_raw"


def test_t_a02_skip_a1_submit_a3_is_step_order(service, project, ep):
    service.create_session(project, ep, SessionCreate(path="A", provider="fixture"))
    try:
        service.submit_step(project, ep, "a3_framework", StepSubmit(frameworks=["惊喜揭秘型"]))
        raise AssertionError("expected step_order")
    except AppError as exc:
        assert exc.status_code == 409
        assert exc.code == "step_order"
        assert exc.details["expected"] == "a1_raw"


def test_t_a03_full_fixture_path_a(service, project, ep):
    service.create_session(project, ep, SessionCreate(path="A", provider="fixture"))
    service.submit_step(project, ep, "a1_raw", StepSubmit(raw_text="咖啡渣别扔，能除臭。"))
    service.submit_step(project, ep, "a2_extract", StepSubmit(decision="approve"))
    service.submit_step(project, ep, "a3_framework", StepSubmit(frameworks=["惊喜揭秘型"]))
    env = service.submit_step(project, ep, "a4_candidates", StepSubmit(decision="continue"))
    assert len(env["session"]["candidates"]) == 5
    env = service.submit_step(project, ep, "a5_finalize", StepSubmit(candidate_id="c1"))
    assert env["session"]["status"] == "awaiting_g1"
    assert env["artifact"]["frontmatter"]["locked"] is False


def test_t_r01_only_current_step_runs(service, project, ep):
    service.create_session(project, ep, SessionCreate(path="A", provider="fixture"))
    try:
        service.submit_step(project, ep, "a5_finalize", StepSubmit(candidate_id="c1"))
        raise AssertionError("expected")
    except AppError as exc:
        assert exc.code == "step_order"
