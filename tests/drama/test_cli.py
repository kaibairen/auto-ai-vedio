from __future__ import annotations

from typer.testing import CliRunner

from aiv_cli.cli import app

runner = CliRunner()


def test_cli_demo_fixture(data_dir, monkeypatch):
    monkeypatch.setenv("AIV_DATA_DIR", str(data_dir))
    monkeypatch.setenv("AIV_LLM_PROVIDER", "fixture")
    result = runner.invoke(app, ["--fixture", "--pretty", "drama", "demo", "--ep", "EP01", "--lane", "female"])
    assert result.exit_code == 0, result.output
    assert "D-N2" in result.output
    assert '"locked": true' in result.output
    assert '"d_n2_started": false' in result.output


def test_cli_lane_required(data_dir, monkeypatch):
    monkeypatch.setenv("AIV_DATA_DIR", str(data_dir))
    runner.invoke(app, ["drama", "project", "create", "--name", "x"])
    # project id is proj_01 on fresh store
    runner.invoke(app, ["drama", "episode", "create", "--project", "proj_01", "--ep", "EP01"])
    runner.invoke(
        app,
        ["drama", "brief", "put", "--project", "proj_01", "--ep", "EP01", "--title-intent", "一句", "--lane", "unset"],
    )
    result = runner.invoke(
        app,
        ["drama", "outline", "generate", "--project", "proj_01", "--ep", "EP01", "--provider", "fixture"],
    )
    assert result.exit_code == 2
    assert "intent_unconfirmed" in result.output
