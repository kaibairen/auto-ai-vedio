from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from aiv_n1.config import DEFAULT_PROJECT_ID
from aiv_n1.errors import AppError
from aiv_n1.models import DraftPayload, EpisodeCreate, SessionCreate, StepSubmit
from aiv_n1.service import N1Service

router = APIRouter(prefix="/api/v0")


def _svc(request: Request) -> N1Service:
    return request.app.state.service


def _actor(body_actor: str | None, x_actor: str | None) -> str | None:
    return body_actor or x_actor


@router.post("/projects/{project_id}/episodes", status_code=201)
def create_episode(project_id: str, body: EpisodeCreate, request: Request) -> dict[str, Any]:
    return _svc(request).create_episode(project_id or DEFAULT_PROJECT_ID, body.ep, title=body.title)


@router.get("/projects/{project_id}/episodes/{ep}")
def get_episode(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    return _svc(request).envelope(project_id, ep)


@router.post("/projects/{project_id}/episodes/{ep}/n1/sessions", status_code=201)
def create_session(project_id: str, ep: str, body: SessionCreate, request: Request) -> dict[str, Any]:
    return _svc(request).create_session(project_id, ep, body)


@router.post("/projects/{project_id}/episodes/{ep}/n1/steps/{step}/submit")
def submit_step(project_id: str, ep: str, step: str, body: StepSubmit, request: Request) -> dict[str, Any]:
    return _svc(request).submit_step(project_id, ep, step, body)


@router.put("/projects/{project_id}/episodes/{ep}/nodes/n1/raw")
def put_raw(project_id: str, ep: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
    text = body.get("raw_text") or body.get("text") or ""
    return _svc(request).put_raw(project_id, ep, text, actor=body.get("actor"))


@router.put("/projects/{project_id}/episodes/{ep}/nodes/n1/draft")
def put_draft_primary(project_id: str, ep: str, body: DraftPayload, request: Request) -> dict[str, Any]:
    return _svc(request).put_draft(project_id, ep, body)


@router.put("/projects/{project_id}/episodes/{ep}/n1/draft")
def put_draft_alias(project_id: str, ep: str, body: DraftPayload, request: Request) -> dict[str, Any]:
    return _svc(request).put_draft(project_id, ep, body)


@router.get("/projects/{project_id}/episodes/{ep}/nodes/n1")
def get_n1_primary(project_id: str, ep: str, request: Request, view: str = "full") -> dict[str, Any]:
    if view not in {"session", "artifact", "full"}:
        raise AppError(400, "validation", "view must be session|artifact|full")
    return _svc(request).get_n1(project_id, ep, view=view)


@router.get("/projects/{project_id}/episodes/{ep}/n1")
def get_n1_alias(project_id: str, ep: str, request: Request, view: str = "full") -> dict[str, Any]:
    if view not in {"session", "artifact", "full"}:
        raise AppError(400, "validation", "view must be session|artifact|full")
    return _svc(request).get_n1(project_id, ep, view=view)


@router.get("/projects/{project_id}/episodes/{ep}/n1/artifact")
@router.get("/projects/{project_id}/episodes/{ep}/nodes/n1/artifact")
@router.get("/projects/{project_id}/episodes/{ep}/n1/final")
def get_n1_downstream(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    return _svc(request).get_artifact_downstream(project_id, ep)


@router.post("/projects/{project_id}/episodes/{ep}/gates/g1/confirm")
async def confirm_g1(
    project_id: str,
    ep: str,
    request: Request,
    x_actor: str | None = Header(default=None, alias="X-Actor"),
) -> dict[str, Any]:
    raw = await request.json()
    if not isinstance(raw, dict):
        raise AppError(400, "validation", "JSON object required")
    if x_actor and not raw.get("actor"):
        raw = {**raw, "actor": x_actor}
    return _svc(request).confirm_g1(project_id, ep, raw)


@router.api_route("/projects/{project_id}/episodes/{ep}/n1/lock", methods=["GET", "POST", "PUT"])
def n1_lock_removed(project_id: str, ep: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "ok": False,
            "error": {
                "code": "not_found",
                "message": "Use POST .../gates/g1/confirm only. No n1/lock, no force_pass.",
                "details": {"confirm_path": f"/api/v0/projects/{project_id}/episodes/{ep}/gates/g1/confirm"},
            },
        },
    )
