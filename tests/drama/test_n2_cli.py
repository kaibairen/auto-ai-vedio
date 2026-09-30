from __future__ import annotations

from typer.testing import CliRunner

from aiv_cli.cli import app

runner = CliRunner()


def test_cli_storyboard_after_demo(data_dir, monkeypatch):
    monkeypatch.setenv("AIV_DATA_DIR", str(data_dir))
    monkeypatch.setenv("AIV_LLM_PROVIDER", "fixture")
    demo = runner.invoke(app, ["--fixture", "--pretty", "drama", "demo", "--ep", "EP01", "--lane", "female"])
    assert demo.exit_code == 0, demo.output
    gen = runner.invoke(
        app,
        ["drama", "storyboard", "generate", "--project", "proj_01", "--ep", "EP01", "--provider", "fixture"],
    )
    assert gen.exit_code == 0, gen.output
    assert "D-N2" in gen.output
    assert "borrowed_dongman" in gen.output
    con = runner.invoke(
        app,
        [
            "drama",
            "g2",
            "confirm",
            "--project",
            "proj_01",
            "--ep",
            "EP01",
            "--decision",
            "pass",
            "--actor",
            "yangzhou",
        ],
    )
    assert con.exit_code == 0, con.output
    assert "D-N3" in con.output
    assert '"locked": true' in con.output


def test_cli_sidecar_add_after_demo(data_dir, monkeypatch):
    monkeypatch.setenv("AIV_DATA_DIR", str(data_dir))
    monkeypatch.setenv("AIV_LLM_PROVIDER", "fixture")
    demo = runner.invoke(app, ["--fixture", "--pretty", "drama", "demo", "--ep", "EP01", "--lane", "female"])
    assert demo.exit_code == 0, demo.output
    add = runner.invoke(
        app,
        [
            "drama",
            "cast",
            "sidecar-add",
            "--project",
            "proj_01",
            "--ep",
            "EP01",
            "--name",
            "CODEX王子",
            "--one-line",
            "弹窗反派",
        ],
    )
    assert add.exit_code == 0, add.output
    assert "CODEX王子" in add.output
    assert "cast_changed" in add.output


def test_cli_storyboard_llm_missing_key(data_dir, monkeypatch):
    monkeypatch.setenv("AIV_DATA_DIR", str(data_dir))
    monkeypatch.setenv("AIV_LLM_PROVIDER", "fixture")
    monkeypatch.delenv("AIV_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    demo = runner.invoke(app, ["--fixture", "--pretty", "drama", "demo", "--ep", "EP01", "--lane", "female"])
    assert demo.exit_code == 0, demo.output
    gen = runner.invoke(
        app,
        ["drama", "storyboard", "generate", "--project", "proj_01", "--ep", "EP01", "--provider", "llm"],
    )
    assert gen.exit_code == 2, gen.output
    assert "AIV_OPENAI_API_KEY" in gen.output
    assert "provider" in gen.output
