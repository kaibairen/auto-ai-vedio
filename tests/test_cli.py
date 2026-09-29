from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from aiv.cli import app

runner = CliRunner()


def test_cli_demo_path_a(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIV_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["n1", "demo", "--project", "demo", "--ep", "EP01", "--path", "A"])
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["locked"] is True
    assert data["path"] == "A"
    assert data["auto_advanced"] is False
    art = Path(data["artifact"]["abs_path"])
    assert art.is_file()
    text = art.read_text(encoding="utf-8")
    assert "node: N1" in text
    assert "locked: true" in text
    assert "bot:demo" in text


def test_cli_downstream_409_then_confirm(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIV_DATA_DIR", str(tmp_path))
    runner.invoke(app, ["n1", "session", "--project", "cli", "--ep", "EP02", "--path", "A"])
    runner.invoke(
        app,
        ["n1", "draft", "--project", "cli", "--ep", "EP02", "--title", "t", "--body", "短口播加一个CTA。"],
    )
    bad = runner.invoke(app, ["n1", "get", "--project", "cli", "--ep", "EP02", "--downstream"])
    assert bad.exit_code == 1
    assert json.loads(bad.stdout)["error"] == "n1_not_locked"
    ok = runner.invoke(
        app,
        ["n1", "confirm", "--project", "cli", "--ep", "EP02", "--decision", "pass", "--actor", "bot:cli"],
    )
    assert ok.exit_code == 0
    assert json.loads(ok.stdout)["locked"] is True
