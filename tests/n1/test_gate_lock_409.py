from __future__ import annotations

from aiv_n1.artifact import read_n1_markdown
from aiv_n1.errors import AppError
from aiv_n1.gates.g1 import require_n1_locked
from aiv_n1.models import DraftPayload, SessionCreate


def _ready(service, project, ep):
    service.create_session(project, ep, SessionCreate(path="A", provider="fixture"))
    service.put_draft(
        project,
        ep,
        DraftPayload(title="咖啡渣别扔", body="每天扔掉的咖啡渣其实能除臭。你还用过它做什么？评论区告诉我。", framework="惊喜揭秘型"),
    )


def test_t_g01_pass_without_draft_409(service, project, ep):
    service.create_session(project, ep, SessionCreate(path="A", provider="fixture"))
    try:
        service.confirm_g1(project, ep, {"decision": "pass", "actor": "bot:ci"})
        raise AssertionError("expected 409")
    except AppError as exc:
        assert exc.status_code == 409


def test_t_g02_pass_locks(service, project, ep):
    _ready(service, project, ep)
    env = service.confirm_g1(project, ep, {"decision": "pass", "actor": "bot:ci"})
    assert env["session"]["status"] == "locked"
    meta, _ = read_n1_markdown(service.store.artifact_path(ep))
    assert meta["locked"] is True
    assert meta["confirmed_by"] == "bot:ci"


def test_t_g03_put_draft_after_lock_409(service, project, ep):
    _ready(service, project, ep)
    service.confirm_g1(project, ep, {"decision": "pass", "actor": "bot:ci"})
    try:
        service.put_draft(project, ep, DraftPayload(title="改", body="锁后不可写。"))
        raise AssertionError("expected locked")
    except AppError as exc:
        assert exc.status_code == 409
        assert exc.code == "locked"


def test_t_g04_reject_returns_finalize(service, project, ep):
    _ready(service, project, ep)
    env = service.confirm_g1(project, ep, {"decision": "reject", "actor": "user:a"})
    assert env["session"]["status"] == "active"
    assert env["session"]["current_step"] == "a5_finalize"
    assert env["session"]["status"] != "locked"


def test_t_g05_force_true_400(service, project, ep):
    _ready(service, project, ep)
    try:
        service.confirm_g1(project, ep, {"decision": "pass", "actor": "admin", "force": True})
        raise AssertionError("expected 400")
    except AppError as exc:
        assert exc.status_code == 400


def test_t_d01_require_n1_locked():
    try:
        require_n1_locked({"locked": False})
        raise AssertionError("expected")
    except AppError as exc:
        assert exc.status_code == 409
        assert exc.code == "upstream_unlocked"
        assert exc.details["node"] == "N1"


def test_t_d02_downstream_ok_after_lock(service, project, ep):
    _ready(service, project, ep)
    try:
        service.get_artifact_downstream(project, ep)
        raise AssertionError("expected 409")
    except AppError as exc:
        assert exc.code == "upstream_unlocked"
    service.confirm_g1(project, ep, {"decision": "pass", "actor": "user:a"})
    env = service.get_artifact_downstream(project, ep)
    assert env["ok"] is True
    assert env["artifact"]["frontmatter"]["locked"] is True


def test_t_r02_no_auto_writer(service, project, ep):
    _ready(service, project, ep)
    env = service.confirm_g1(project, ep, {"decision": "pass", "actor": "bot:ci"})
    assert env["auto_advanced"] is False
    assert {e["to"] for e in env["next_edges"]} == {"writer", "n2"}
    names = {p.name for p in service.store.episode_dir(ep).iterdir() if p.is_file()}
    assert "N1-口播定稿.md" in names
    assert "EP01-大纲.md" not in names
