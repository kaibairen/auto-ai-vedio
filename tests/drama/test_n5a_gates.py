"""AIV-036 N5a min loop. ForcePass=never. No fake pixels. Mode B / EP01 EXEMPT nails."""

from __future__ import annotations

import hashlib
from pathlib import Path

from typer.testing import CliRunner

from aiv_cli.cli import app
from aiv_drama.errors import AppError
from aiv_drama_n3.models import N3MaterializeRequest
from aiv_drama_n5a.checklist import build_checklist
from aiv_drama_n5a.exempt import SCENE_NA_REASON, scene_look_exempt
from aiv_drama_n5a.image import assert_real_image_bytes, generate_grid_image
from aiv_drama_n5a.look_mode import MODE_B, look_mode_for_char, missing_face_is_hard_block
from aiv_drama_n5a.models import N5aGenerateRequest
from tests.drama.helpers import (
    MINIMAL_PNG,
    lock_g2,
    plant_prompts_jsonl,
    seed_project_episode,
    thicken_mode_b_char,
)

runner = CliRunner()


def _err(fn):
    try:
        fn()
    except AppError as exc:
        return exc
    raise AssertionError("expected AppError")


def _setup_mode_b(svc):
    pid = seed_project_episode(svc)
    lock_g2(svc, pid, tool_profile="seedance_2")
    svc.materialize_n3_cards(pid, "EP01", N3MaterializeRequest(actor="yangzhou"))
    thicken_mode_b_char(svc, pid)
    plant_prompts_jsonl(svc, pid)
    return pid


def _mock_grid(bytes_out: bytes = MINIMAL_PNG, model: str = "doubao-seedream-5-0-flash-260915"):
    def _gen(**_kwargs):
        return {
            "model": model,
            "bytes": bytes_out,
            "attempts": [{"model": model, "http": 200, "status": "ok", "image": True}],
            "size": "2048x2048",
            "has_image_ref": False,
        }

    return _gen


def test_missing_jsonl_is_409(svc, data_dir):
    pid = seed_project_episode(svc)
    exc = _err(lambda: svc.generate_n5a_grid(pid, "EP01", N5aGenerateRequest(actor="yangzhou"), raw={"actor": "yangzhou"}))
    assert exc.status_code == 409
    assert exc.code == "missing_prompts_jsonl"
    assert exc.details.get("written") is False
    ep = Path(data_dir) / "projects" / pid / "episodes" / "EP01" / "grids"
    assert not list(ep.glob("*_grid_*.png")) if ep.exists() else True


def test_empty_jsonl_is_409(svc, data_dir):
    pid = seed_project_episode(svc)
    ep_dir = Path(data_dir) / "projects" / pid / "episodes" / "EP01"
    ep_dir.mkdir(parents=True, exist_ok=True)
    (ep_dir / "EP01-prompts.jsonl").write_text("", encoding="utf-8")
    exc = _err(lambda: svc.generate_n5a_grid(pid, "EP01", N5aGenerateRequest(), raw={}))
    assert exc.status_code == 409
    assert exc.code == "missing_prompts_jsonl"


def test_force_pass_generate_and_g4_are_400(svc):
    pid = _setup_mode_b(svc)
    for key in ("force_pass", "force", "skip_gate"):
        exc = _err(
            lambda k=key: svc.generate_n5a_grid(
                pid, "EP01", N5aGenerateRequest(actor="yangzhou"), raw={"actor": "yangzhou", k: True}
            )
        )
        assert exc.status_code == 400
        assert exc.code == "force_pass_forbidden"
        exc2 = _err(lambda k=key: svc.confirm_gate_g4(pid, "EP01", {"verdict": "pass", "actor": "yangzhou", k: True}))
        assert exc2.status_code == 400
        assert exc2.code == "force_pass_forbidden"


def test_mode_b_does_not_require_face_file(svc, data_dir, monkeypatch):
    pid = _setup_mode_b(svc)
    rec = svc._rec(pid, "EP01")
    char = rec["n3"]["cards"]["characters"][0]
    assert look_mode_for_char(char) == MODE_B
    assert not any((r.get("role") in {"face", "full"}) for r in (char.get("refs") or []))
    assert missing_face_is_hard_block(mode=MODE_B) is False
    monkeypatch.setattr("aiv_drama_n5a.ops.generate_grid_image", _mock_grid())
    env = svc.generate_n5a_grid(pid, "EP01", N5aGenerateRequest(actor="yangzhou"), raw={"actor": "yangzhou"})
    assert env["written"] is True
    assert env["mode_b_face_required"] is False
    assert env["look_modes"].get("CHAR-01") == MODE_B
    assert env["md5"]
    grid = Path(data_dir) / "projects" / pid / env["path"]
    assert grid.is_file()
    assert hashlib.md5(grid.read_bytes()).hexdigest() == env["md5"]
    assert grid.read_bytes().startswith(b"\x89PNG")


def test_missing_api_key_is_block_no_fake_grid(svc, data_dir, monkeypatch):
    pid = _setup_mode_b(svc)

    def _no_key(*, api_key, **kwargs):
        return generate_grid_image(api_key="", prompt=kwargs.get("prompt") or "p")

    monkeypatch.setattr("aiv_drama_n5a.ops.generate_grid_image", _no_key)
    exc = _err(lambda: svc.generate_n5a_grid(pid, "EP01", N5aGenerateRequest(actor="yangzhou"), raw={"actor": "yangzhou"}))
    assert exc.status_code == 422
    assert exc.code == "provider"
    assert exc.details.get("blocked") is True
    assert exc.details.get("written") is False
    assert exc.details.get("fake_pixels") is False
    grids = Path(data_dir) / "projects" / pid / "episodes" / "EP01" / "grids"
    assert not list(grids.glob("*_grid_*.png")) if grids.exists() else True


def test_fake_pixel_bytes_rejected():
    exc = _err(lambda: assert_real_image_bytes(b"COLORBARS-PLACEHOLDER_GRID"))
    assert exc.code == "fake_pixels_forbidden"
    exc2 = _err(lambda: assert_real_image_bytes(b""))
    assert exc2.code == "fake_pixels_forbidden"
    assert_real_image_bytes(MINIMAL_PNG)


def test_mock_api_fake_bytes_do_not_write(svc, data_dir, monkeypatch):
    pid = _setup_mode_b(svc)
    monkeypatch.setattr("aiv_drama_n5a.ops.generate_grid_image", _mock_grid(b"COLORBARS"))
    exc = _err(lambda: svc.generate_n5a_grid(pid, "EP01", N5aGenerateRequest(actor="x"), raw={"actor": "x"}))
    assert exc.code == "fake_pixels_forbidden"
    grids = Path(data_dir) / "projects" / pid / "episodes" / "EP01" / "grids"
    assert not list(grids.glob("*_grid_*.png")) if grids.exists() else True


def test_ep01_scene_exempt_g4_item_na(svc, monkeypatch):
    pid = _setup_mode_b(svc)
    rec = svc._rec(pid, "EP01")
    assert scene_look_exempt(rec, "EP01") is True
    monkeypatch.setattr("aiv_drama_n5a.ops.generate_grid_image", _mock_grid())
    env = svc.generate_n5a_grid(pid, "EP01", N5aGenerateRequest(actor="yangzhou"), raw={"actor": "yangzhou"})
    items = env["checklist"]["items"]
    assert items["G4"]["verdict"] == SCENE_NA_REASON
    assert items["G4"]["hard"] is False
    assert env["scene_exempt"] is True
    for ident in ("G1", "G2", "G3", "G9"):
        assert items[ident]["verdict"] == "pending"
        assert items[ident]["hard"] is True
    assert env["threshold_hard_gated"] is False
    assert "≥7/9" in env["checklist"]["threshold_note"] or "7/9" in env["checklist"]["threshold_note"]


def test_g4_pass_and_rework_persisted(svc, monkeypatch):
    pid = _setup_mode_b(svc)
    monkeypatch.setattr("aiv_drama_n5a.ops.generate_grid_image", _mock_grid())
    svc.generate_n5a_grid(pid, "EP01", N5aGenerateRequest(actor="yangzhou"), raw={"actor": "yangzhou"})
    rework = svc.confirm_gate_g4(pid, "EP01", {"verdict": "rework", "actor": "yangzhou", "note": "手畸"})
    assert rework["gate"]["last_decision"] == "rework"
    assert rework["gate"]["locked"] is False
    assert rework["g4_locked"] is False
    assert rework["gate"]["actor"] == "yangzhou"
    passed = svc.confirm_gate_g4(pid, "EP01", {"verdict": "pass", "actor": "cam-036"})
    assert passed["gate"]["last_decision"] == "pass"
    assert passed["gate"]["locked"] is True
    assert passed["g4_locked"] is True
    assert passed["gate"]["actor"] == "cam-036"
    st = svc.get_n5a_status(pid, "EP01")
    assert st["g4_locked"] is True
    assert st["g4_verdict"] == "pass"
    assert st["auto_open_dn5b"] is False


def test_g4_pass_without_grid_is_409(svc):
    pid = _setup_mode_b(svc)
    exc = _err(lambda: svc.confirm_gate_g4(pid, "EP01", {"verdict": "pass", "actor": "yangzhou"}))
    assert exc.status_code == 409
    assert exc.code == "missing_grid"


def test_n5b_submit_out_of_pr(svc, monkeypatch):
    pid = _setup_mode_b(svc)
    exc = _err(lambda: svc.submit_n5b(pid, "EP01", raw={"actor": "yangzhou"}))
    assert exc.status_code == 409
    assert exc.code == "upstream_unlocked"
    monkeypatch.setattr("aiv_drama_n5a.ops.generate_grid_image", _mock_grid())
    svc.generate_n5a_grid(pid, "EP01", N5aGenerateRequest(actor="yangzhou"), raw={"actor": "yangzhou"})
    svc.confirm_gate_g4(pid, "EP01", {"verdict": "pass", "actor": "yangzhou"})
    exc2 = _err(lambda: svc.submit_n5b(pid, "EP01", raw={"actor": "yangzhou"}))
    assert exc2.status_code == 404
    assert exc2.code == "n5b_not_implemented"


def test_layout_25_rejected(svc):
    pid = _setup_mode_b(svc)
    exc = _err(lambda: svc.generate_n5a_grid(pid, "EP01", N5aGenerateRequest(layout=25), raw={"layout": 25}))
    assert exc.status_code == 422
    assert exc.code == "validation"


def test_dry_run_does_not_write_png_or_pass_g4(svc, data_dir):
    pid = _setup_mode_b(svc)
    env = svc.generate_n5a_grid(
        pid, "EP01", N5aGenerateRequest(actor="yangzhou", dry_run=True), raw={"actor": "yangzhou", "dry_run": True}
    )
    assert env["dry_run"] is True
    assert env["written"] is False
    grids = Path(data_dir) / "projects" / pid / "episodes" / "EP01" / "grids"
    assert not list(grids.glob("*_grid_*.png"))
    exc = _err(lambda: svc.confirm_gate_g4(pid, "EP01", {"verdict": "pass", "actor": "yangzhou"}))
    assert exc.code == "missing_grid"


def test_image_client_missing_key_block():
    exc = _err(lambda: generate_grid_image(api_key="", prompt="p"))
    assert exc.code == "provider"
    assert exc.details.get("blocked") is True
    assert exc.details.get("fake_pixels") is False


def test_http_n5a_flow(client, monkeypatch):
    from tests.drama.test_n4_api import _setup_g3_usable

    pid = _setup_g3_usable(client)
    svc = client.app.state.service
    thicken_mode_b_char(svc, pid)
    plant_prompts_jsonl(svc, pid)
    missing = client.post(f"/api/v0/projects/{pid}/episodes/EP02/drama/n5a/generate", json={})
    # EP02 does not exist
    assert missing.status_code in {404, 422, 409}
    banned = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n5a/generate",
        json={"actor": "yangzhou", "force_pass": True},
    )
    assert banned.status_code == 400
    assert banned.json()["error"]["code"] == "force_pass_forbidden"
    monkeypatch.setattr("aiv_drama_n5a.ops.generate_grid_image", _mock_grid())
    gen = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n5a/generate",
        json={"actor": "yangzhou", "layout": 9},
    )
    assert gen.status_code == 200, gen.text
    body = gen.json()
    assert body["written"] is True
    assert body["layout"] == 9
    assert body["md5"]
    assert body["checklist"]["items"]["G4"]["verdict"] == SCENE_NA_REASON
    assert body["mode_b_face_required"] is False
    assert body["auto_open_dn5b"] is False
    g4 = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/gates/g4",
        json={"verdict": "pass", "actor": "yangzhou"},
    )
    assert g4.status_code == 200, g4.text
    assert g4.json()["g4_locked"] is True
    st = client.get(f"/api/v0/projects/{pid}/episodes/EP01/drama/n5a/status")
    assert st.status_code == 200
    assert st.json()["g4_locked"] is True
    n5b = client.post(f"/api/v0/projects/{pid}/episodes/EP01/drama/n5b/jobs", json={"actor": "yangzhou"})
    assert n5b.status_code == 404
    assert n5b.json()["error"]["code"] == "n5b_not_implemented"
    bare = client.get(f"/api/v0/projects/{pid}/episodes/EP01/n5a")
    assert bare.status_code == 404


def test_http_missing_jsonl_409(client):
    from tests.drama.test_n3_api import _setup_g2

    pid = _setup_g2(client)
    res = client.post(f"/api/v0/projects/{pid}/episodes/EP01/drama/n5a/generate", json={"actor": "yangzhou"})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "missing_prompts_jsonl"


def test_cli_generate_grid_missing_jsonl(data_dir, monkeypatch):
    monkeypatch.setenv("AIV_DATA_DIR", str(data_dir))
    monkeypatch.setenv("AIV_LLM_PROVIDER", "fixture")
    runner.invoke(app, ["drama", "project", "create", "--name", "x"])
    runner.invoke(app, ["drama", "episode", "create", "--project", "proj_01", "--ep", "EP01"])
    result = runner.invoke(
        app,
        ["drama", "n5a", "generate-grid", "--project", "proj_01", "--ep", "EP01", "--actor", "yangzhou"],
    )
    assert result.exit_code == 3
    assert "missing_prompts_jsonl" in result.output


def test_health_and_openapi_n5a(client):
    data = client.get("/health").json()
    assert "D-N5a" in data["nodes"]
    assert "g4" in data["gates"]
    assert data["auto_open_dn5b"] is False
    spec = client.get("/openapi/drama-n5a.v0.yaml")
    assert spec.status_code == 200
    text = spec.text
    assert "D-N5a" in text
    assert "force_pass_forbidden" in text
    assert "missing_prompts_jsonl" in text
    assert "Mode B" in text
    assert "SCENE EXEMPT" in text or "SCENE-LOOK-EXEMPT" in text or "N/A" in text
    assert "n5b_not_implemented" in text
    assert "fake" in text.lower() or "假像素" in text


def test_checklist_builder_exempt_other_ep():
    rec = {"episode": {"episode_id": "EP02"}}
    sheet = build_checklist(
        rec=rec,
        ep="EP02",
        layout=9,
        grid_relpath="episodes/EP02/grids/EP02_grid_9_v1.png",
        md5="abc",
        sku="x",
    )
    assert sheet["items"]["G4"]["verdict"] == "pending"
    assert sheet["scene_exempt"] is False
    assert sheet["threshold_hard_gated"] is False
