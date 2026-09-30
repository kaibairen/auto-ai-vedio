from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import typer
import uvicorn

from aiv_api.app import create_app
from aiv_drama.config import Settings
from aiv_drama.errors import AppError
from aiv_drama.models import (
    AttachRequest,
    DetachRequest,
    DramaBriefWrite,
    EpisodeCreate,
    LibraryCharacterWrite,
    OutlineGenerateRequest,
    OutlineResetRequest,
    OutlineWrite,
    ProjectCreate,
)
from aiv_drama.service import DramaService
from aiv_drama_n2.models import (
    StoryboardGenerateRequest,
    StoryboardReorderRequest,
    StoryboardResetRequest,
    StoryboardWrite,
)

app = typer.Typer(name="aiv", help="Drama D-N0 / D-N1 / D-N2 CLI. JSON envelope on stdout. Isolated from koubo-N1.")
drama = typer.Typer(help="短剧 D-N0 / D-N1 / D-N2")
project_app = typer.Typer(help="Project stub")
episode_app = typer.Typer(help="Episode (pipeline_profile=drama)")
library_app = typer.Typer(help="Project-scoped character seed (not list/search)")
brief_app = typer.Typer(help="D-N0 brief")
outline_app = typer.Typer(help="D-N1 outline")
cast_app = typer.Typer(help="D-N1 cast")
gate_app = typer.Typer(help="Gate G1b")
downstream_app = typer.Typer(help="D-N2 consumer read (does not start D-N2)")
storyboard_app = typer.Typer(help="D-N2 storyboard")
g2_app = typer.Typer(help="Gate G2")

app.add_typer(drama, name="drama")
drama.add_typer(project_app, name="project")
drama.add_typer(episode_app, name="episode")
drama.add_typer(library_app, name="library")
drama.add_typer(brief_app, name="brief")
drama.add_typer(outline_app, name="outline")
drama.add_typer(cast_app, name="cast")
drama.add_typer(gate_app, name="gate")
drama.add_typer(downstream_app, name="downstream")
drama.add_typer(storyboard_app, name="storyboard")
drama.add_typer(g2_app, name="g2")

_PRETTY = False


def _print(data: object) -> None:
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2 if _PRETTY else None))


def _service() -> DramaService:
    return DramaService(Settings.from_env())


def _exit_for(exc: AppError) -> int:
    if exc.status_code == 400:
        return 1
    if exc.status_code == 422:
        return 2
    if exc.status_code == 409:
        return 3
    if exc.status_code == 404:
        return 4
    return 1


def _guard(fn):  # type: ignore[no-untyped-def]
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


@project_app.command("create")
def project_create(name: str = typer.Option(..., "--name")) -> None:
    _print(_guard(lambda: _service().create_project(ProjectCreate(name=name))))


@project_app.command("get")
def project_get(project_id: str = typer.Option(..., "--project")) -> None:
    _print(_guard(lambda: _service().get_project(project_id)))


@episode_app.command("create")
def episode_create(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
    title: Optional[str] = typer.Option(None, "--title"),
) -> None:
    body = EpisodeCreate(episode_id=ep, pipeline_profile="drama", title=title)
    _print(_guard(lambda: _service().create_episode(project_id, body)))


@episode_app.command("get")
def episode_get(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
) -> None:
    _print(_guard(lambda: _service().get_episode(project_id, ep)))


@library_app.command("put")
def library_put(
    project_id: str = typer.Option(..., "--project"),
    character_id: str = typer.Option(..., "--character-id"),
    version: int = typer.Option(1, "--version"),
    name: str = typer.Option(..., "--name"),
    one_line: str = typer.Option(..., "--one-line"),
) -> None:
    body = LibraryCharacterWrite(name=name, one_line=one_line, version=version)
    _print(_guard(lambda: _service().put_library_character(project_id, character_id, body)))


@brief_app.command("get")
def brief_get(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
) -> None:
    _print(_guard(lambda: _service().get_brief(project_id, ep)))


@brief_app.command("put")
def brief_put(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
    title_intent: Optional[str] = typer.Option(None, "--title-intent"),
    lane: str = typer.Option("unset", "--lane"),
    setting_notes: Optional[str] = typer.Option(None, "--setting-notes"),
    actor: Optional[str] = typer.Option(None, "--actor"),
    confirm_stale_outline: bool = typer.Option(False, "--confirm-stale-outline"),
) -> None:
    body = DramaBriefWrite(
        title_intent=title_intent,
        lane_preference=lane,  # type: ignore[arg-type]
        setting_notes=setting_notes,
        actor=actor,
        confirm_stale_outline=confirm_stale_outline,
    )
    _print(_guard(lambda: _service().put_brief(project_id, ep, body, raw=body.model_dump())))


@outline_app.command("get")
def outline_get(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
) -> None:
    _print(_guard(lambda: _service().get_outline(project_id, ep)))


@outline_app.command("generate")
def outline_generate(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
    lane: Optional[str] = typer.Option(None, "--lane"),
    provider: str = typer.Option("fixture", "--provider"),
    shot_cap: int = typer.Option(12, "--shot-cap"),
    actor: Optional[str] = typer.Option(None, "--actor"),
) -> None:
    body = OutlineGenerateRequest(
        lane=lane,  # type: ignore[arg-type]
        provider=provider,  # type: ignore[arg-type]
        shot_cap=shot_cap,
        actor=actor,
    )
    env = _guard(lambda: _service().generate_outline(project_id, ep, body, raw=body.model_dump(exclude_none=True)))
    if isinstance(env, dict):
        for item in env.get("warnings") or []:
            typer.echo(f"warning: {item}", err=True)
    _print(env)


@outline_app.command("put")
def outline_put(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
    body_md: str = typer.Option(..., "--body-md"),
    unlock_edit: bool = typer.Option(False, "--unlock-edit"),
) -> None:
    body = OutlineWrite(body_md=body_md, unlock_edit=unlock_edit)
    _print(_guard(lambda: _service().put_outline(project_id, ep, body, raw=body.model_dump())))


@outline_app.command("reset")
def outline_reset(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
    clear_cast: bool = typer.Option(False, "--clear-cast"),
    unlock_edit: bool = typer.Option(False, "--unlock-edit"),
) -> None:
    body = OutlineResetRequest(clear_cast=clear_cast, unlock_edit=unlock_edit)
    _print(_guard(lambda: _service().reset_outline(project_id, ep, body, raw=body.model_dump())))


@cast_app.command("get")
def cast_get(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
) -> None:
    _print(_guard(lambda: _service().get_cast(project_id, ep)))


@cast_app.command("attach")
def cast_attach(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
    character_id: str = typer.Option(..., "--character-id"),
    version: int = typer.Option(..., "--version"),
    unlock_edit: bool = typer.Option(False, "--unlock-edit"),
    actor: Optional[str] = typer.Option(None, "--actor"),
) -> None:
    body = AttachRequest(character_id=character_id, version=version, unlock_edit=unlock_edit, actor=actor)
    _print(_guard(lambda: _service().attach_character(project_id, ep, body, raw=body.model_dump())))


@cast_app.command("detach")
def cast_detach(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
    character_id: str = typer.Option(..., "--character-id"),
    unlock_edit: bool = typer.Option(False, "--unlock-edit"),
) -> None:
    body = DetachRequest(character_id=character_id, unlock_edit=unlock_edit)
    _print(_guard(lambda: _service().detach_character(project_id, ep, body, raw=body.model_dump())))


@gate_app.command("get")
def gate_get(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
) -> None:
    _print(_guard(lambda: _service().get_gate(project_id, ep)))


@gate_app.command("confirm")
def gate_confirm(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
    decision: str = typer.Option(..., "--decision"),
    actor: str = typer.Option(..., "--actor"),
    note: Optional[str] = typer.Option(None, "--note"),
) -> None:
    raw = {"decision": decision, "actor": actor}
    if note is not None:
        raw["note"] = note
    _print(_guard(lambda: _service().confirm_gate(project_id, ep, raw)))


@downstream_app.command("get")
def downstream_get(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
) -> None:
    _print(_guard(lambda: _service().get_downstream(project_id, ep)))


@storyboard_app.command("get")
def storyboard_get(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
) -> None:
    _print(_guard(lambda: _service().get_storyboard(project_id, ep)))


@storyboard_app.command("generate")
def storyboard_generate(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
    provider: str = typer.Option("fixture", "--provider"),
    tool_profile: Optional[str] = typer.Option(None, "--tool-profile"),
    unlock_edit: bool = typer.Option(False, "--unlock-edit"),
    actor: Optional[str] = typer.Option(None, "--actor"),
) -> None:
    body = StoryboardGenerateRequest(
        provider=provider,  # type: ignore[arg-type]
        tool_profile=tool_profile,  # type: ignore[arg-type]
        unlock_edit=unlock_edit,
        actor=actor,
    )
    _print(
        _guard(
            lambda: _service().generate_storyboard(
                project_id, ep, body, raw=body.model_dump(exclude_none=True)
            )
        )
    )


@storyboard_app.command("put")
def storyboard_put(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
    file: str = typer.Option(..., "--file", help="JSON object with rows[] (StoryboardWrite)"),
    unlock_edit: bool = typer.Option(False, "--unlock-edit"),
    actor: Optional[str] = typer.Option(None, "--actor"),
) -> None:
    raw = json.loads(Path(file).read_text(encoding="utf-8"))
    if unlock_edit:
        raw["unlock_edit"] = True
    if actor:
        raw["actor"] = actor
    body = StoryboardWrite.model_validate(raw)
    _print(_guard(lambda: _service().put_storyboard(project_id, ep, body, raw=raw)))


@storyboard_app.command("validate")
def storyboard_validate(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
) -> None:
    _print(_guard(lambda: _service().validate_storyboard(project_id, ep)))


@storyboard_app.command("reorder")
def storyboard_reorder(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
    shot_ids: str = typer.Option(..., "--shot-ids", help="Comma-separated S01,S02,..."),
    actor: Optional[str] = typer.Option(None, "--actor"),
) -> None:
    ids = [s.strip() for s in shot_ids.split(",") if s.strip()]
    body = StoryboardReorderRequest(shot_ids=ids, actor=actor)
    _print(_guard(lambda: _service().reorder_storyboard(project_id, ep, body, raw=body.model_dump())))


@storyboard_app.command("reset")
def storyboard_reset(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
    unlock_edit: bool = typer.Option(False, "--unlock-edit"),
    actor: Optional[str] = typer.Option(None, "--actor"),
) -> None:
    body = StoryboardResetRequest(unlock_edit=unlock_edit, actor=actor)
    _print(_guard(lambda: _service().reset_storyboard(project_id, ep, body, raw=body.model_dump())))


@g2_app.command("get")
def g2_get(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
) -> None:
    _print(_guard(lambda: _service().get_gate_g2(project_id, ep)))


@g2_app.command("confirm")
def g2_confirm(
    project_id: str = typer.Option(..., "--project"),
    ep: str = typer.Option(..., "--ep"),
    decision: str = typer.Option(..., "--decision"),
    actor: str = typer.Option(..., "--actor"),
    note: Optional[str] = typer.Option(None, "--note"),
) -> None:
    raw = {"decision": decision, "actor": actor}
    if note is not None:
        raw["note"] = note
    _print(_guard(lambda: _service().confirm_gate_g2(project_id, ep, raw)))


@drama.command("demo")
def demo(
    name: str = typer.Option("短剧狗粮-01", "--name"),
    ep: str = typer.Option("EP01", "--ep"),
    lane: str = typer.Option("female", "--lane"),
    actor: str = typer.Option("yangzhou", "--actor"),
) -> None:
    """Fixture happy path: project → brief (D-N0) → generate (D-N1) → G1b pass."""

    def _run() -> dict:
        svc = _service()
        proj = svc.create_project(ProjectCreate(name=name))["project"]
        pid = proj["id"]
        svc.put_library_character(
            pid,
            "CHAR-01",
            LibraryCharacterWrite(name="林晚", one_line="重生女主", version=1),
        )
        svc.create_episode(pid, EpisodeCreate(episode_id=ep, pipeline_profile="drama", title="第一集"))
        svc.put_brief(
            pid,
            ep,
            DramaBriefWrite(title_intent="被流放的庶女在边关翻盘", lane_preference=lane, actor=actor),  # type: ignore[arg-type]
        )
        svc.attach_character(pid, ep, AttachRequest(character_id="CHAR-01", version=1, actor=actor))
        outline = svc.generate_outline(
            pid, ep, OutlineGenerateRequest(lane=lane, provider="fixture"), raw={"lane": lane, "provider": "fixture"}  # type: ignore[arg-type]
        )
        gate = svc.confirm_gate(pid, ep, {"decision": "pass", "actor": actor, "note": "ok"})
        return {
            "ok": True,
            "project_id": pid,
            "episode_id": ep,
            "node": "D-N1",
            "lane": outline["outline"]["lane"],
            "locked": gate["gate"]["locked"],
            "confirmed_by": gate["outline"]["confirmed_by"],
            "next_edges": gate["next_edges"],
            "d_n2_started": False,
            "jobs": [],
        }

    _print(_guard(_run))
