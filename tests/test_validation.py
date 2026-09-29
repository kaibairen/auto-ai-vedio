from __future__ import annotations

from aiv.errors import AppError
from aiv.models import DraftPayload, SessionCreate, SubmitPayload
from aiv.validation import count_chars, validate_char_limit


def test_count_chars_skips_whitespace():
    assert count_chars("你好 世界\n") == 4


def test_path_a_rejects_over_400(service, project, ep):
    service.create_session(project, ep, SessionCreate(path="A", provider="fixture"))
    body = "字" * 401
    try:
        service.put_draft(project, ep, DraftPayload(title="超了", body=body))
        raise AssertionError("expected char_limit")
    except AppError as exc:
        assert exc.code == "char_limit"
        assert exc.extra["limit"] == 400
        assert exc.extra["chars"] == 401


def test_path_a_accepts_400(service, project, ep):
    service.create_session(project, ep, SessionCreate(path="A", provider="fixture"))
    view = service.put_draft(project, ep, DraftPayload(title="刚好", body="字" * 400))
    assert view["draft"]["chars"] == 400
    assert view["artifact"]["frontmatter"]["chars"] == 400


def test_path_b_rejects_over_500(service, project, ep):
    service.create_session(project, ep, SessionCreate(path="B", provider="fixture"))
    try:
        service.put_draft(project, ep, DraftPayload(title="短标题", body="字" * 501))
        raise AssertionError("expected char_limit")
    except AppError as exc:
        assert exc.code == "char_limit"
        assert exc.extra["limit"] == 500


def test_validate_char_limit_helper():
    assert validate_char_limit("A", "a" * 400) == 400
    try:
        validate_char_limit("B", "b" * 501)
        raise AssertionError("expected")
    except AppError as exc:
        assert exc.extra["limit"] == 500


def test_step_1_requires_text(service, project, ep):
    service.create_session(project, ep, SessionCreate(path="A", provider="fixture"))
    try:
        service.submit_step(project, ep, 1, SubmitPayload(text=""))
        raise AssertionError("expected raw_required")
    except AppError as exc:
        assert exc.code == "raw_required"
