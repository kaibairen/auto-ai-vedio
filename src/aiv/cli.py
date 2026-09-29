from __future__ import annotations

import json
import os
from typing import Optional

import typer
import uvicorn

from aiv.api.app import create_app
from aiv.config import Settings
from aiv.errors import AppError
from aiv.models import DraftPayload, GateConfirm, SessionCreate, SubmitPayload
from aiv.service import N1Service

app = typer.Typer(name="aiv", help="N1 口播定稿 CLI (fixture by default, no API key required).")
n1_app = typer.Typer(help="N1 session / draft / G1 confirm")
app.add_typer(n1_app, name="n1")


def _print(data: object) -> None:
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


def _service() -> N1Service:
    return N1Service(Settings.from_env())


def _guard(fn):
    try:
        return fn()
    except AppError as exc:
        _print(exc.to_dict())
        raise typer.Exit(code=1) from exc


@app.callback()
def _root(
    data_dir: Optional[str] = typer.Option(None, "--data-dir", envvar="AIV_DATA_DIR"),
    provider: Optional[str] = typer.Option(None, "--provider", envvar="AIV_LLM_PROVIDER"),
) -> None:
    if data_dir:
        os.environ["AIV_DATA_DIR"] = data_dir
    if provider:
        os.environ["AIV_LLM_PROVIDER"] = provider


@app.command("serve")
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Start REST + minimal N1 wizard at /."""
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


@n1_app.command("init")
def n1_init(
    project: str = typer.Option("demo", "--project"),
    ep: str = typer.Option("EP01", "--ep"),
    title: str = typer.Option("", "--title"),
) -> None:
    _print(_guard(lambda: _service().create_episode(project, ep, title=title or None)))


@n1_app.command("session")
def n1_session(
    project: str = typer.Option("demo", "--project"),
    ep: str = typer.Option("EP01", "--ep"),
    path: str = typer.Option("A", "--path", help="A=口水话, B=长文章"),
    provider: str = typer.Option("fixture", "--provider"),
) -> None:
    body = SessionCreate(path=path.upper(), provider=provider)  # type: ignore[arg-type]
    _print(_guard(lambda: _service().create_session(project, ep, body)))


@n1_app.command("submit")
def n1_submit(
    project: str = typer.Option("demo", "--project"),
    ep: str = typer.Option("EP01", "--ep"),
    step: int = typer.Option(..., "--step"),
    text: str = typer.Option("", "--text"),
    notes: str = typer.Option("", "--notes"),
    frameworks: str = typer.Option("", "--frameworks", help="comma-separated names or ids"),
    pick: Optional[int] = typer.Option(None, "--pick"),
    title: str = typer.Option("", "--title"),
) -> None:
    payload = SubmitPayload(
        text=text,
        notes=notes,
        frameworks=[p.strip() for p in frameworks.split(",") if p.strip()],
        pick=pick,
        title=title or None,
        confirm=True,
    )
    _print(_guard(lambda: _service().submit_step(project, ep, step, payload)))


@n1_app.command("draft")
def n1_draft(
    project: str = typer.Option("demo", "--project"),
    ep: str = typer.Option("EP01", "--ep"),
    title: str = typer.Option("", "--title"),
    body: str = typer.Option(..., "--body"),
    framework: str = typer.Option("", "--framework"),
) -> None:
    payload = DraftPayload(title=title, body=body, framework=framework or None)
    _print(_guard(lambda: _service().put_draft(project, ep, payload)))


@n1_app.command("get")
def n1_get(
    project: str = typer.Option("demo", "--project"),
    ep: str = typer.Option("EP01", "--ep"),
    downstream: bool = typer.Option(False, "--downstream", help="409 if not locked"),
) -> None:
    consumer = "downstream" if downstream else "authoring"
    _print(_guard(lambda: _service().get_n1(project, ep, consumer=consumer)))


@n1_app.command("confirm")
def n1_confirm(
    project: str = typer.Option("demo", "--project"),
    ep: str = typer.Option("EP01", "--ep"),
    decision: str = typer.Option(..., "--decision", help="pass|reject"),
    actor: str = typer.Option(..., "--actor", help="written to confirmed_by"),
    notes: str = typer.Option("", "--notes"),
    rollback_to: Optional[int] = typer.Option(None, "--rollback-to"),
) -> None:
    if decision not in {"pass", "reject"}:
        _print({"error": "invalid_decision", "message": "decision must be pass or reject"})
        raise typer.Exit(code=1)
    body = GateConfirm(decision=decision, actor=actor, notes=notes, rollback_to=rollback_to)  # type: ignore[arg-type]
    raw = {"decision": decision, "actor": actor, "notes": notes, "rollback_to": rollback_to}
    _print(_guard(lambda: _service().confirm_g1(project, ep, body, raw_payload=raw)))


@n1_app.command("demo")
def n1_demo(
    project: str = typer.Option("demo", "--project"),
    ep: str = typer.Option("EP01", "--ep"),
    path: str = typer.Option("A", "--path"),
    actor: str = typer.Option("bot:demo", "--actor"),
) -> None:
    """One-shot fixture walk: steps → N1-口播定稿.md → G1 pass."""
    result = _guard(lambda: _service().demo(project, ep, path.upper(), actor=actor))
    _print(result)
    art = (result.get("artifact") or {}).get("abs_path")
    if art:
        typer.echo(f"\n# wrote {art}", err=True)
