from __future__ import annotations

from aiv_n1.errors import AppError
from aiv_n1.models import DraftPayload, SessionCreate
from aiv_n1.validate import count_chars, draft_chars, validate_char_limit


def test_nfc_code_point_count_includes_internal_space():
    assert count_chars("你好 世界") == 5
    assert draft_chars("题", "正文") == 3


def test_path_a_rejects_over_400(service, project, ep):
    service.create_session(project, ep, SessionCreate(path="A", provider="fixture"))
    try:
        service.put_draft(project, ep, DraftPayload(title="T", body="字" * 400))
        raise AssertionError("expected chars_limit")
    except AppError as exc:
        assert exc.code == "chars_limit"
        assert exc.status_code == 422
        assert exc.details["limit"] == 400


def test_path_a_accepts_400_total(service, project, ep):
    service.create_session(project, ep, SessionCreate(path="A", provider="fixture"))
    env = service.put_draft(project, ep, DraftPayload(title="", body="字" * 400))
    assert env["session"]["draft"]["chars"] == 400


def test_path_b_rejects_501(service, project, ep):
    service.create_session(project, ep, SessionCreate(path="B", provider="fixture"))
    try:
        service.put_draft(project, ep, DraftPayload(title="短标题", body="字" * 501))
        raise AssertionError("expected")
    except AppError as exc:
        assert exc.code == "chars_limit"
        assert exc.details["limit"] == 500


def test_validate_helper():
    assert validate_char_limit("A", 400) == 400
    try:
        validate_char_limit("B", 501)
        raise AssertionError("expected")
    except AppError as exc:
        assert exc.details["actual"] == 501


def test_t_a04_candidate_401(service, project, ep, monkeypatch):
    from aiv_n1.models import StepSubmit
    from aiv_n1.provider.base import GenerateResponse

    class Bad:
        name = "fixture"

        def generate(self, req):
            if req.kind == "generate_candidates":
                return GenerateResponse(
                    kind="candidates",
                    message="x",
                    candidates=[{"id": "c1", "title": "t", "body": "字" * 401, "framework": "惊喜揭秘型"}],
                )
            from aiv_n1.provider.fixture import FixtureProvider

            return FixtureProvider().generate(req)

    monkeypatch.setattr("aiv_n1.service.get_provider", lambda *_a, **_k: Bad())
    service.create_session(project, ep, SessionCreate(path="A", provider="fixture"))
    service.submit_step(project, ep, "a1_raw", StepSubmit(raw_text="咖啡渣。"))
    service.submit_step(project, ep, "a2_extract", StepSubmit(decision="approve"))
    service.submit_step(project, ep, "a3_framework", StepSubmit(frameworks=["惊喜揭秘型"]))
    try:
        service.submit_step(project, ep, "a4_candidates", StepSubmit(decision="continue"))
        raise AssertionError("expected chars_limit")
    except AppError as exc:
        assert exc.code == "chars_limit"
        assert exc.details["limit"] == 400
