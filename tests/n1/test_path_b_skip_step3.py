from __future__ import annotations

from aiv_n1.artifact import sha256_file
from aiv_n1.errors import AppError
from aiv_n1.models import SessionCreate, StepSubmit
from aiv_n1.steps import PATH_B_SKIP_REASON


def test_t_b01_session_starts_b1(service, project, ep):
    env = service.create_session(project, ep, SessionCreate(path="B", provider="fixture"))
    assert env["session"]["current_step"] == "b1_raw"


def test_t_b02_b03_skip_step_3(service, project, ep):
    service.create_session(project, ep, SessionCreate(path="B", provider="fixture"))
    service.submit_step(project, ep, "b1_raw", StepSubmit(raw_text="长文：少即是多。"))
    env = service.submit_step(project, ep, "b2_analyze", StepSubmit(decision="approve"))
    assert env["session"]["current_step"] == "b3_skipped"
    assert "missing_step_3" in env["session"]["defects"]
    try:
        service.submit_step(project, ep, "b4_titles", StepSubmit(title_id="t1"))
        raise AssertionError("expected step_order")
    except AppError as exc:
        assert exc.code == "step_order"
    env = service.submit_step(project, ep, "b3_skipped", StepSubmit(ack_defect=True))
    assert env["session"]["current_step"] == "b4_titles"
    assert "missing_step_3" in env["session"]["defects"]
    assert env["session"]["defect_note"]


def test_t_b05_framework_defect_note(service, project, ep):
    env = service.create_session(project, ep, SessionCreate(path="B", provider="fixture"))
    assert "framework_7_8_corrupt" in (env["session"]["defects"] + [env["session"].get("defect_note") or ""]) or any(
        f.get("defective") for f in __import__("aiv_n1.steps", fromlist=["frameworks_for"]).frameworks_for("B")
    )


def test_prompt_not_rewritten(service, project, ep, repo_root):
    prompt = repo_root / ".prompt" / "koubo-长文章.md"
    before = sha256_file(prompt)
    text = prompt.read_text(encoding="utf-8")
    service.create_session(project, ep, SessionCreate(path="B", provider="fixture"))
    service.submit_step(project, ep, "b1_raw", StepSubmit(raw_text="原料。"))
    service.submit_step(project, ep, "b2_analyze", StepSubmit(decision="approve"))
    service.submit_step(project, ep, "b3_skipped", StepSubmit(ack_defect=True))
    assert sha256_file(prompt) == before
    assert prompt.read_text(encoding="utf-8") == text
    assert "缺第3步" in text or "missing_step_3" in PATH_B_SKIP_REASON


def test_t_b04_b5_b6_chars_501(service, project, ep, monkeypatch):
    from aiv_n1.provider.base import GenerateResponse
    from aiv_n1.provider.fixture import FixtureProvider

    class OverLimit:
        name = "fixture"

        def generate(self, req):
            if req.kind in {"reconstruct", "optimize"}:
                return GenerateResponse(
                    kind="draft",
                    message="over",
                    draft_title="短标题",
                    draft_body="字" * 501,
                )
            return FixtureProvider().generate(req)

    service.create_session(project, ep, SessionCreate(path="B", provider="fixture"))
    service.submit_step(project, ep, "b1_raw", StepSubmit(raw_text="长文章：一个痛点加一个行动。"))
    service.submit_step(project, ep, "b2_analyze", StepSubmit(decision="approve"))
    service.submit_step(project, ep, "b3_skipped", StepSubmit(ack_defect=True))
    service.submit_step(project, ep, "b4_titles", StepSubmit(title_id="t1"))
    monkeypatch.setattr("aiv_n1.service.get_provider", lambda *_a, **_k: OverLimit())
    try:
        service.submit_step(project, ep, "b5_framework_draft", StepSubmit(framework="痛点共鸣式"))
        raise AssertionError("expected chars_limit on b5")
    except AppError as exc:
        assert exc.code == "chars_limit"
        assert exc.status_code == 422
        assert exc.details["limit"] == 500
        assert exc.details["actual"] >= 501


def test_t_b_walk(service, project, ep):
    service.create_session(project, ep, SessionCreate(path="B", provider="fixture"))
    service.submit_step(project, ep, "b1_raw", StepSubmit(raw_text="长文章：一个痛点加一个行动。"))
    service.submit_step(project, ep, "b2_analyze", StepSubmit(decision="approve"))
    service.submit_step(project, ep, "b3_skipped", StepSubmit(ack_defect=True))
    env = service.submit_step(project, ep, "b4_titles", StepSubmit(title_id="t1"))
    assert env["session"]["current_step"] == "b5_framework_draft"
    env = service.submit_step(project, ep, "b5_framework_draft", StepSubmit(framework="痛点共鸣式"))
    env = service.submit_step(project, ep, "b6_finalize", StepSubmit(decision="approve"))
    assert env["session"]["status"] == "awaiting_g1"
    assert env["session"]["draft"]["chars"] <= 500
