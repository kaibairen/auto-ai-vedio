from __future__ import annotations

from aiv.errors import AppError
from aiv.models import SessionCreate, SubmitPayload


def _open(service, project, ep, path="A"):
    service.create_episode(project, ep)
    return service.create_session(project, ep, SessionCreate(path=path, provider="fixture"))


def test_cannot_jump_from_step_1_to_4(service, project, ep):
    _open(service, project, ep)
    try:
        service.submit_step(project, ep, 4, SubmitPayload(confirm=True))
        raise AssertionError("expected step_not_allowed")
    except AppError as exc:
        assert exc.status_code == 409
        assert exc.code == "step_not_allowed"
        assert exc.extra["allowed_steps"] == [1]


def test_submit_in_order_opens_only_next_step(service, project, ep):
    _open(service, project, ep)
    view = service.submit_step(project, ep, 1, SubmitPayload(text="咖啡渣别扔，能除臭。"))
    assert view["allowed_steps"] == [2]
    assert view["completed_steps"] == [1]
    view = service.submit_step(project, ep, 2, SubmitPayload(confirm=True))
    assert view["allowed_steps"] == [3]


def test_cannot_resubmit_completed_step(service, project, ep):
    _open(service, project, ep)
    service.submit_step(project, ep, 1, SubmitPayload(text="原料一句。"))
    try:
        service.submit_step(project, ep, 1, SubmitPayload(text="另一句。"))
        raise AssertionError("expected step_not_allowed")
    except AppError as exc:
        assert exc.code == "step_not_allowed"
        assert 1 not in exc.extra["allowed_steps"]


def test_machine_readable_step_spec_and_candidates(service, project, ep):
    _open(service, project, ep)
    service.submit_step(project, ep, 1, SubmitPayload(text="咖啡渣别扔，能除臭还能当肥料。"))
    service.submit_step(project, ep, 2, SubmitPayload(confirm=True))
    view = service.submit_step(project, ep, 3, SubmitPayload(frameworks=["惊喜揭秘型"]))
    assert view["step_spec"]["kind"] == "generate_candidates"
    view = service.submit_step(project, ep, 4, SubmitPayload(confirm=True))
    assert len(view["candidates"]) == 5
    assert all("title" in c and "body" in c and "chars" in c for c in view["candidates"])
    assert view["session_id"]
    assert view["prompt_source"] == ".prompt/koubo-口水话.md"
