"""AIV-036 N5b HTTP + CLI + OpenAPI. Zero paid Job calls."""

from __future__ import annotations

from typer.testing import CliRunner

from aiv_cli.cli import app
from tests.drama.helpers import sample_n5b_line, seed_project_episode, stamp_g4_locked, write_n5b_jsonl

runner = CliRunner()


def test_health_lists_dn5b(client):
    data = client.get("/health").json()
    assert "D-N5b" in data["nodes"]
    assert "g4" in data["gates"]
    assert "g5" in data["gates"]
    assert data["auto_open_dn5"] is False
    assert data["auto_open_dn6"] is False
    assert data["docs_pass"] is False


def test_openapi_n5b_copy_served(client):
    res = client.get("/openapi/drama-n5b.v0.yaml")
    assert res.status_code == 200
    text = res.text
    assert "0.1.0" in text
    assert "D-N5b" in text
    assert "g4_required" in text
    assert "live_job_forbidden" in text
    assert "n5b_impl_hold" in text
    assert "force_pass_forbidden" in text
    assert "doubao-seedance-2-0-260128" in text
    assert "/contents/generations/tasks" in text
    assert "2.35:1" in text
    assert "a11e4b39460139ef8d4dac78ef86768a" in text


def test_http_submit_g4_then_live_block(client):
    svc = client.app.state.service
    pid = seed_project_episode(svc)
    write_n5b_jsonl(svc, pid, [sample_n5b_line()])
    blocked = client.post(f"/api/v0/projects/{pid}/episodes/EP01/drama/n5b/jobs", json={"actor": "yangzhou"})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "g4_required"
    stamp_g4_locked(svc, pid)
    dry = client.post(f"/api/v0/projects/{pid}/episodes/EP01/drama/n5b/jobs", json={"actor": "yangzhou"})
    assert dry.status_code == 409
    err = dry.json()["error"]
    assert err["code"] == "live_job_forbidden"
    assert err["details"]["posted"] is False
    st = client.get(f"/api/v0/projects/{pid}/episodes/EP01/drama/n5b/status")
    assert st.status_code == 200
    body = st.json()
    assert body["skeleton"] is True
    assert body["posted"] is False
    assert body["mode_b_look_blocks"] is False
    assert body["g4_locked"] is True
    job = client.get(f"/api/v0/projects/{pid}/episodes/EP01/drama/n5b/jobs/cgt-none")
    assert job.status_code == 404


def test_http_force_pass_and_g5_rework(client):
    svc = client.app.state.service
    pid = seed_project_episode(svc)
    stamp_g4_locked(svc, pid)
    res = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/drama/n5b/jobs",
        json={"actor": "yangzhou", "force_pass": True},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "force_pass_forbidden"
    g5 = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/gates/g5/confirm",
        json={"verdict": "rework", "actor": "yangzhou"},
    )
    assert g5.status_code == 200
    assert g5.json()["gate"]["last_decision"] == "rework"
    g5p = client.post(
        f"/api/v0/projects/{pid}/episodes/EP01/gates/g5/confirm",
        json={"decision": "pass", "actor": "yangzhou"},
    )
    assert g5p.status_code == 409
    assert g5p.json()["error"]["code"] == "clips_required"


def test_http_bare_n5b_isolated(client):
    svc = client.app.state.service
    pid = seed_project_episode(svc)
    res = client.get(f"/api/v0/projects/{pid}/episodes/EP01/n5b")
    assert res.status_code == 404
    assert "/drama/n5b" in res.json()["error"]["message"]


def test_cli_submit_blocks(svc, data_dir, monkeypatch):
    monkeypatch.setenv("AIV_DATA_DIR", str(data_dir))
    monkeypatch.setenv("AIV_LLM_PROVIDER", "fixture")
    monkeypatch.delenv("AIV_N5B_ALLOW_LIVE_JOB", raising=False)
    pid = seed_project_episode(svc)
    write_n5b_jsonl(svc, pid, [sample_n5b_line()])
    stamp_g4_locked(svc, pid)
    result = runner.invoke(app, ["drama", "n5b", "submit", "--project", pid, "--ep", "EP01", "--actor", "yangzhou"])
    assert result.exit_code == 3, result.output
    assert "live_job_forbidden" in result.output
    assert '"posted": false' in result.output
    st = runner.invoke(app, ["drama", "n5b", "status", "--project", pid, "--ep", "EP01"])
    assert st.exit_code == 0, st.output
    assert "D-N5b" in st.output
    g5 = runner.invoke(
        app,
        ["drama", "n5b", "gate", "g5", "--project", pid, "--ep", "EP01", "--actor", "yangzhou", "--verdict", "rework"],
    )
    assert g5.exit_code == 0, g5.output
    assert "rework" in g5.output
