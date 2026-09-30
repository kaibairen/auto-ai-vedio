"""021c · library schema + attach/promote stubs. D12–D15 hanging."""

from __future__ import annotations

from pathlib import Path

from aiv_drama.errors import AppError
from aiv_drama_n3.models import LibrarySceneWrite, N3AttachRequest, N3MaterializeRequest, N3PromoteRequest
from aiv_drama_n3.policy import hanging_bundle

from tests.drama.helpers import lock_g2, seed_project_episode


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def test_library_schema_characters_and_scene_stub(svc, data_dir):
    pid = seed_project_episode(svc)
    root = Path(data_dir) / "projects" / pid / "libraries" / "characters" / "CHAR-01"
    assert (root / "character.yaml").is_file()
    text = (root / "character.yaml").read_text(encoding="utf-8")
    assert "project_scope" in text
    assert "pending_hanging" in text
    assert "chosen" in text
    assert (root / "v3" / "character.yaml").is_file()
    assert (root / "v3" / "card.md").is_file()
    svc.put_library_scene(pid, "SCENE-01", LibrarySceneWrite(name="边关营帐", one_line="对峙空间", version=1))
    scene_root = Path(data_dir) / "projects" / pid / "libraries" / "scenes" / "SCENE-01"
    assert (scene_root / "scene.yaml").is_file()
    scene_yaml = (scene_root / "scene.yaml").read_text(encoding="utf-8")
    assert "template_status: deferred" in scene_yaml
    assert "template_path: null" in scene_yaml or "template_path:" in scene_yaml
    pol = svc.get_library_policy(pid)
    assert pol["project_scope"] == "project"
    assert pol["project_scope_capability"]["chosen"] is None
    assert pol["project_scope_capability"]["status"] == "pending_hanging"
    bundle = hanging_bundle()
    assert bundle["d13_promote"]["auto_promote"] is False
    assert bundle["d13_promote"]["chosen"] is None
    lib = svc.get_library(pid)
    assert lib["characters"]
    assert any(s["id"] == "SCENE-01" for s in lib["scenes"])


def test_attach_does_not_skip_g3(svc):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    env = svc.attach_n3_card(
        pid,
        "EP01",
        N3AttachRequest(id="CHAR-01", version=3, actor="yangzhou"),
        raw={"id": "CHAR-01", "version": 3},
    )
    assert env["g3_skipped"] is False
    assert env["gate"]["locked"] is False
    assert env["cards"]["locked"] is False
    binding = next(c["binding"] for c in env["cards"]["characters"] if c["id"] == "CHAR-01")
    assert "CHAR-01@3" in binding
    assert svc._rec(pid, "EP01")["gate_g3"]["state"] != "passed"


def test_promote_does_not_auto_pass_g3(svc, data_dir):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    before = svc._rec(pid, "EP01")["gate_g3"]
    env = svc.promote_n3_card(
        pid,
        "EP01",
        N3PromoteRequest(id="CHAR-01", actor="yangzhou"),
        raw={"id": "CHAR-01", "actor": "yangzhou"},
    )
    assert env["g3_auto_passed"] is False
    assert env["gate_g3_unchanged"] is True
    after = svc._rec(pid, "EP01")["gate_g3"]
    assert after["locked"] is False
    assert after["state"] == before["state"]
    root = Path(data_dir) / "projects" / pid / "libraries" / "characters" / "CHAR-01"
    versions = list((root).glob("v*/card.md"))
    assert versions
    exc = _err(
        lambda: svc.promote_n3_card(
            pid,
            "EP01",
            N3PromoteRequest(id="CHAR-01", actor="yangzhou"),
            raw={"id": "CHAR-01", "auto_promote": True},
        )
    )
    assert exc.status_code == 400
    assert exc.code == "auto_promote_forbidden"
    assert svc._rec(pid, "EP01")["gate_g3"]["locked"] is False


def test_fork_is_hanging_stub(svc):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid)
    from aiv_drama_n3.models import N3ForkRequest

    env = svc.fork_n3_card(pid, "EP01", N3ForkRequest(id="CHAR-01", actor="yangzhou"), raw={"id": "CHAR-01"})
    assert env["stub"] is True
    assert env["written"] is False
    assert env["chosen"] is None
    assert env["hanging"]["decision"] == "D15"
