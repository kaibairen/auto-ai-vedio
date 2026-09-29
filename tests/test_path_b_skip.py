from __future__ import annotations

from aiv.artifact import sha256_file
from aiv.curriculum import PATH_B_SKIP_REASON
from aiv.errors import AppError
from aiv.models import SessionCreate, SubmitPayload


def test_path_b_skips_step_3_and_forbids_submit(service, project, ep):
    service.create_session(project, ep, SessionCreate(path="B", provider="fixture"))
    view = service.submit_step(project, ep, 1, SubmitPayload(text="一篇关于坚持写作的长文章，核心是少即是多。"))
    assert 3 in view["skipped_steps"]
    view = service.submit_step(project, ep, 2, SubmitPayload(confirm=True))
    assert view["allowed_steps"] == [4]
    assert view["current_step"] == 4
    try:
        service.submit_step(project, ep, 3, SubmitPayload(confirm=True))
        raise AssertionError("expected source_defect_skip")
    except AppError as exc:
        assert exc.status_code == 400
        assert exc.code == "source_defect_skip"
        assert exc.extra["step"] == 3
        assert "koubo-长文章.md" in exc.message


def test_path_b_walks_1_2_4_5_6(service, project, ep):
    service.create_session(project, ep, SessionCreate(path="B", provider="fixture"))
    service.submit_step(project, ep, 1, SubmitPayload(text="长文章：少即是多，先讲一个痛点再给一个行动。"))
    service.submit_step(project, ep, 2, SubmitPayload(confirm=True))
    view = service.submit_step(project, ep, 4, SubmitPayload(confirm=True))
    assert len(view["titles"]) == 3
    view = service.submit_step(project, ep, 5, SubmitPayload(frameworks=["痛点共鸣式"], pick=0))
    assert view["allowed_steps"] == [6]
    view = service.submit_step(project, ep, 6, SubmitPayload(notes="再短一点"))
    assert view["state"] == "awaiting_gate"
    assert view["draft"]["chars"] <= 500
    assert view["artifact"]["frontmatter"]["locked"] is False


def test_path_b_does_not_rewrite_prompt(service, project, ep, repo_root):
    prompt = repo_root / ".prompt" / "koubo-长文章.md"
    before = sha256_file(prompt)
    text = prompt.read_text(encoding="utf-8")
    service.create_session(project, ep, SessionCreate(path="B", provider="fixture"))
    service.submit_step(project, ep, 1, SubmitPayload(text="原料。"))
    service.submit_step(project, ep, 2, SubmitPayload(confirm=True))
    try:
        service.submit_step(project, ep, 3, SubmitPayload(confirm=True))
    except AppError:
        pass
    after = sha256_file(prompt)
    assert after == before
    assert prompt.read_text(encoding="utf-8") == text
    assert "缺第3步" in text or "缺第3步" in PATH_B_SKIP_REASON
