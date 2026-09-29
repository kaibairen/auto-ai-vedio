from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import typer
import uvicorn

from aiv_api.app import create_app
from aiv_n1.config import DEFAULT_PROJECT_ID, Settings
from aiv_n1.errors import AppError
from aiv_n1.models import DraftPayload, SessionCreate, StepSubmit
from aiv_n1.service import N1Service

app = typer.Typer(name="aiv", help="N1 口播定稿 CLI. JSON envelope on stdout.")
n1_app = typer.Typer(help="N1")
n1_session = typer.Typer(help="N1 sessions")
n1_step = typer.Typer(help="N1 steps")
n1_draft = typer.Typer(help="N1 draft")
n1_gate = typer.Typer(help="N1 G1")
gate_app = typer.Typer(help="Gates")
ep_app = typer.Typer(help="Episodes")

app.add_typer(n1_app, name="n1")
app.add_typer(gate_app, name="gate")
app.add_typer(ep_app, name="ep")
n1_app.add_typer(n1_session, name="session")
n1_app.add_typer(n1_step, name="step")
n1_app.add_typer(n1_draft, name="draft")
n1_app.add_typer(n1_gate, name="gate")

_PRETTY = False


def _print(data: object) -> None:
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2 if _PRETTY else None))


def _service() -> N1Service:
    return N1Service(Settings.from_env())


def _exit_for(exc: AppError) -> int:
    if exc.code in {"chars_limit", "validation"}:
        return 2
    if exc.status_code == 409 or exc.code in {"step_order", "locked", "upstream_unlocked", "conflict"}:
        return 3
    return 1


def _guard(fn):
    try:
        return fn()
    except AppError as exc:
        _print(exc.to_envelope())
        raise typer.Exit(code=_exit_for(exc)) from exc


@app.callback()
def _root(
    data_dir: Optional[str] = typer.Option(None, "--data-dir", envvar="AIV_DATA_DIR"),
    provider: Optional[str] = typer.Option(None, "--provider", envvar="AIV_LLM_PROVIDER"),
    pretty: bool = typer.Option(False, "--pretty"),
    fixture: bool = typer.Option(False, "--fixture"),
) -> None:
    global _PRETTY
    _PRETTY = pretty
    if data_dir:
        os.environ["AIV_DATA_DIR"] = data_dir
    if fixture:
        os.environ["AIV_LLM_PROVIDER"] = "fixture"
    elif provider:
        os.environ["AIV_LLM_PROVIDER"] = provider


@app.command("serve")
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


@ep_app.command("create")
def ep_create(
    ep: str = typer.Argument("EP01"),
    project: str = typer.Option(DEFAULT_PROJECT_ID, "--project"),
) -> None:
    _print(_guard(lambda: _service().create_episode(project, ep)))


def _start_session(project: str, ep: str, path: str, provider: str, reset: bool = False) -> dict:
    body = SessionCreate(path=path.upper(), provider=provider, reset=reset)  # type: ignore[arg-type]
    return _service().create_session(project, ep, body)


@n1_session.command("start")
@n1_session.command("create")
def session_start(
    ep: str = typer.Option("EP01", "--ep"),
    path: str = typer.Option("A", "--path"),
    provider: str = typer.Option("fixture", "--provider"),
    project: str = typer.Option(DEFAULT_PROJECT_ID, "--project"),
    reset: bool = typer.Option(False, "--reset"),
) -> None:
    _print(_guard(lambda: _start_session(project, ep, path, provider, reset)))


@n1_app.command("start")
def n1_start(
    ep: str = typer.Argument("EP01"),
    path: str = typer.Option("A", "--path"),
    provider: str = typer.Option("fixture", "--provider"),
    project: str = typer.Option(DEFAULT_PROJECT_ID, "--project"),
) -> None:
    _print(_guard(lambda: _start_session(project, ep, path, provider)))


@n1_app.command("raw")
def n1_raw(
    ep: str = typer.Argument(...),
    path: str = typer.Option("A", "--path"),
    file: Path = typer.Option(..., "--file"),
    project: str = typer.Option(DEFAULT_PROJECT_ID, "--project"),
) -> None:
    def run():
        svc = _service()
        if not svc._load_session(ep):
            _start_session(project, ep, path, "fixture")
        return svc.put_raw(project, ep, file.read_text(encoding="utf-8"))

    _print(_guard(run))


@n1_step.command("submit")
def step_submit(
    ep: str = typer.Option("EP01", "--ep"),
    step: str = typer.Option(..., "--step"),
    raw_file: Optional[Path] = typer.Option(None, "--raw-file"),
    payload: Optional[str] = typer.Option(None, "--payload"),
    project: str = typer.Option(DEFAULT_PROJECT_ID, "--project"),
    session: Optional[str] = typer.Option(None, "--session"),
) -> None:
    raw: dict = json.loads(payload) if payload else {}
    if raw_file:
        raw["raw_text"] = raw_file.read_text(encoding="utf-8")
    body = StepSubmit.model_validate(raw)
    _print(_guard(lambda: _service().submit_step(project, ep, step, body)))


@n1_draft.command("put")
def draft_put(
    ep: str = typer.Option("EP01", "--ep"),
    title: str = typer.Option("", "--title"),
    body_file: Optional[Path] = typer.Option(None, "--body-file"),
    file: Optional[Path] = typer.Option(None, "--file"),
    framework: str = typer.Option("", "--framework"),
    project: str = typer.Option(DEFAULT_PROJECT_ID, "--project"),
) -> None:
    if file:
        payload = DraftPayload(markdown=file.read_text(encoding="utf-8"), framework=framework or None)
    else:
        body = body_file.read_text(encoding="utf-8") if body_file else ""
        payload = DraftPayload(title=title, body=body, framework=framework or None)
    _print(_guard(lambda: _service().put_draft(project, ep, payload)))


@n1_app.command("get")
def n1_get(
    ep: str = typer.Option("EP01", "--ep"),
    project: str = typer.Option(DEFAULT_PROJECT_ID, "--project"),
    json_flag: bool = typer.Option(True, "--json/--no-json"),
    downstream: bool = typer.Option(False, "--downstream"),
) -> None:
    def run():
        if downstream:
            return _service().get_artifact_downstream(project, ep)
        return _service().get_n1(project, ep)

    _print(_guard(run))


@n1_app.command("confirm")
def n1_confirm(
    ep: str = typer.Argument("EP01"),
    actor: str = typer.Option("user", "--actor"),
    decision: str = typer.Option(..., "--decision"),
    project: str = typer.Option(DEFAULT_PROJECT_ID, "--project"),
    notes: str = typer.Option("", "--notes"),
) -> None:
    result = _guard(lambda: _service().confirm_g1(project, ep, {"decision": decision, "actor": actor, "notes": notes}))
    _print(result)
    if decision == "reject":
        raise typer.Exit(4)


@n1_gate.command("g1")
def n1_gate_g1(
    ep: str = typer.Option("EP01", "--ep"),
    decision: str = typer.Option(..., "--decision"),
    actor: str = typer.Option("bot:cli", "--actor"),
    project: str = typer.Option(DEFAULT_PROJECT_ID, "--project"),
) -> None:
    result = _guard(lambda: _service().confirm_g1(project, ep, {"decision": decision, "actor": actor}))
    _print(result)
    if decision == "reject":
        raise typer.Exit(4)


@gate_app.command("confirm")
def gate_confirm(
    ep: str = typer.Option("EP01", "--ep"),
    gate: str = typer.Option("g1", "--gate"),
    result: str = typer.Option(..., "--result"),
    actor: str = typer.Option("bot:demo", "--actor"),
    project: str = typer.Option(DEFAULT_PROJECT_ID, "--project"),
) -> None:
    if gate != "g1":
        raise typer.Exit(2)
    out = _guard(lambda: _service().confirm_g1(project, ep, {"result": result, "actor": actor}))
    _print(out)
    if result == "reject":
        raise typer.Exit(4)


@n1_app.command("demo")
def n1_demo(
    project: str = typer.Option(DEFAULT_PROJECT_ID, "--project"),
    ep: str = typer.Option("EP01", "--ep"),
    path: str = typer.Option("A", "--path"),
    actor: str = typer.Option("bot:demo", "--actor"),
) -> None:
    result = _guard(lambda: _service().demo(project, ep, path.upper(), actor=actor))
    _print(result)
