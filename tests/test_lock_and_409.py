from __future__ import annotations

from aiv.artifact import read_n1_markdown
from aiv.errors import AppError
from aiv.models import DraftPayload, GateConfirm, SessionCreate


def _draft(service, project, ep, path="A"):
    service.create_session(project, ep, SessionCreate(path=path, provider="fixture"))
    service.put_draft(
        project,
        ep,
        DraftPayload(title="咖啡渣别扔", body="每天扔掉的咖啡渣其实能除臭。你还用过它做什么？评论区告诉我。"),
    )


def test_downstream_get_409_before_lock(service, project, ep):
    _draft(service, project, ep)
    try:
        service.get_n1(project, ep, consumer="downstream")
        raise AssertionError("expected 409")
    except AppError as exc:
        assert exc.status_code == 409
        assert exc.code == "n1_not_locked"
        assert exc.extra["locked"] is False


def test_authoring_get_ok_before_lock(service, project, ep):
    _draft(service, project, ep)
    view = service.get_n1(project, ep, consumer="authoring")
    assert view["locked"] is False
    assert view["artifact"]["exists"] is True


def test_g1_pass_locks_artifact(service, project, ep):
    _draft(service, project, ep)
    view = service.confirm_g1(
        project,
        ep,
        GateConfirm(decision="pass", actor="bot:ci"),
        raw_payload={"decision": "pass", "actor": "bot:ci"},
    )
    assert view["locked"] is True
    assert view["auto_advanced"] is False
    assert view["next_edges"]
    assert all(e["status"] == "blocked" for e in view["next_edges"])
    assert any(e["requires_decision"] == "D2" for e in view["next_edges"])
    meta, _ = read_n1_markdown(service.store.artifact_path(project, ep))
    assert meta["node"] == "N1"
    assert meta["locked"] is True
    assert meta["confirmed_by"] == "bot:ci"
    assert meta["path"] == "A"
    assert int(meta["version"]) >= 1
    assert int(meta["chars"]) > 0


def test_downstream_ok_after_lock(service, project, ep):
    _draft(service, project, ep)
    service.confirm_g1(project, ep, GateConfirm(decision="pass", actor="user:a"), {"decision": "pass", "actor": "user:a"})
    view = service.get_n1(project, ep, consumer="downstream")
    assert view["locked"] is True
    assert "文案内容" in view["artifact"]["markdown"] or view["artifact"]["body"]


def test_force_pass_rejected(service, project, ep):
    _draft(service, project, ep)
    try:
        service.confirm_g1(
            project,
            ep,
            GateConfirm(decision="pass", actor="admin", force_pass=True),
            raw_payload={"decision": "pass", "actor": "admin", "force_pass": True},
        )
        raise AssertionError("expected force_pass_forbidden")
    except AppError as exc:
        assert exc.code == "force_pass_forbidden"


def test_put_draft_after_lock_unlocks_and_bumps_version(service, project, ep):
    _draft(service, project, ep)
    service.confirm_g1(project, ep, GateConfirm(decision="pass", actor="bot:ci"), {"decision": "pass", "actor": "bot:ci"})
    before = read_n1_markdown(service.store.artifact_path(project, ep))[0]
    view = service.put_draft(project, ep, DraftPayload(title="改一版", body="这是锁后升版的新草稿，需要重新走门 G1。"))
    after = read_n1_markdown(service.store.artifact_path(project, ep))[0]
    assert view["locked"] is False
    assert after["locked"] is False
    assert int(after["version"]) == int(before["version"]) + 1


def test_confirm_requires_actor(service, project, ep):
    _draft(service, project, ep)
    try:
        service.confirm_g1(project, ep, GateConfirm(decision="pass", actor=""), {"decision": "pass", "actor": ""})
        raise AssertionError("expected actor_required")
    except AppError as exc:
        assert exc.code == "actor_required"
