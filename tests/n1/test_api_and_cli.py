from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from aiv_cli.cli import app

runner = CliRunner()


def test_http_force_true_400(client, project, ep):
    client.post(f"/api/v0/projects/{project}/episodes", json={"ep": ep})
    client.post(
        f"/api/v0/projects/{project}/episodes/{ep}/n1/sessions",
        json={"path": "A", "provider": "fixture"},
    )
    client.put(
        f"/api/v0/projects/{project}/episodes/{ep}/nodes/n1/draft",
        json={"title": "t", "body": "有钩子的短口播。评论区见。", "framework": "惊喜揭秘型"},
    )
    r = client.post(
        f"/api/v0/projects/{project}/episodes/{ep}/gates/g1/confirm",
        json={"decision": "pass", "actor": "admin", "force": True},
    )
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_http_path_b_b3(client, project, ep):
    client.post(f"/api/v0/projects/{project}/episodes/{ep}/n1/sessions", json={"path": "B", "provider": "fixture"})
    client.post(
        f"/api/v0/projects/{project}/episodes/{ep}/n1/steps/b1_raw/submit",
        json={"raw_text": "长文：一个痛点一个行动。"},
    )
    r = client.post(
        f"/api/v0/projects/{project}/episodes/{ep}/n1/steps/b2_analyze/submit",
        json={"decision": "approve"},
    )
    assert r.json()["session"]["current_step"] == "b3_skipped"
    r = client.post(
        f"/api/v0/projects/{project}/episodes/{ep}/n1/steps/b4_titles/submit",
        json={"title_id": "t1"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "step_order"
    r = client.post(
        f"/api/v0/projects/{project}/episodes/{ep}/n1/steps/b3_skipped/submit",
        json={"ack_defect": True},
    )
    assert r.status_code == 200
    assert r.json()["session"]["current_step"] == "b4_titles"


def test_t_g06_n1_lock_absent(client, project, ep):
    r = client.post(f"/api/v0/projects/{project}/episodes/{ep}/n1/lock", json={})
    assert r.status_code == 404


def test_http_step_order_and_confirm(client, project, ep):
    r = client.post(f"/api/v0/projects/{project}/episodes", json={"ep": ep})
    assert r.status_code == 201
    r = client.post(
        f"/api/v0/projects/{project}/episodes/{ep}/n1/sessions",
        json={"path": "A", "provider": "fixture"},
    )
    assert r.status_code == 201
    assert r.json()["session"]["current_step"] == "a1_raw"
    r = client.post(
        f"/api/v0/projects/{project}/episodes/{ep}/n1/steps/a3_framework/submit",
        json={"frameworks": ["惊喜揭秘型"]},
    )
    assert r.status_code == 409
    assert r.json()["ok"] is False
    assert r.json()["error"]["code"] == "step_order"
    r = client.put(
        f"/api/v0/projects/{project}/episodes/{ep}/nodes/n1/draft",
        json={"title": "钩子", "body": "三秒内把痛点说完。评论区扣1。", "framework": "惊喜揭秘型"},
    )
    assert r.status_code == 200
    r = client.get(f"/api/v0/projects/{project}/episodes/{ep}/n1/artifact")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "upstream_unlocked"
    r = client.post(
        f"/api/v0/projects/{project}/episodes/{ep}/gates/g1/confirm",
        json={"decision": "pass", "actor": "bot:http"},
    )
    assert r.status_code == 200
    assert r.json()["session"]["status"] == "locked"
    assert r.json()["auto_advanced"] is False
    r = client.get(f"/api/v0/projects/{project}/episodes/{ep}/nodes/n1/artifact")
    assert r.status_code == 200


def test_t_c01_cli_get_json(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIV_DATA_DIR", str(tmp_path))
    start = runner.invoke(app, ["n1", "session", "start", "--ep", "EP01", "--path", "A"])
    assert start.exit_code == 0, start.stdout
    got = runner.invoke(app, ["n1", "get", "--ep", "EP01", "--json"])
    assert got.exit_code == 0, got.stdout
    data = json.loads(got.stdout)
    assert data["ok"] is True
    assert data["session"]["status"] == "active"


def test_t_c02_cli_demo_and_downstream(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIV_DATA_DIR", str(tmp_path))
    demo = runner.invoke(app, ["--fixture", "n1", "demo", "--ep", "EP01", "--path", "A"])
    assert demo.exit_code == 0, demo.stdout
    data = json.loads(demo.stdout)
    assert data["session"]["status"] == "locked"
    art = Path(data["artifact"]["abs_path"])
    assert art.is_file()
    text = art.read_text(encoding="utf-8")
    assert "node: N1" in text
    assert "locked: true" in text
    assert "bot:demo" in text
    assert str(tmp_path / "episodes" / "EP01") in str(art)
