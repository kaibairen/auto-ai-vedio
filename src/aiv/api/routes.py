from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from aiv.errors import AppError
from aiv.models import DraftPayload, EpisodeCreate, GateConfirm, SessionCreate, SubmitPayload
from aiv.service import N1Service

router = APIRouter(prefix="/api/v0")


def _svc(request: Request) -> N1Service:
    return request.app.state.service


@router.post("/projects/{project_id}/episodes")
def create_episode(project_id: str, body: EpisodeCreate, request: Request) -> dict[str, Any]:
    return _svc(request).create_episode(project_id, body.ep, title=body.title)


@router.get("/projects/{project_id}/episodes/{ep}")
def get_episode(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    return _svc(request).get_episode(project_id, ep)


@router.post("/projects/{project_id}/episodes/{ep}/n1/sessions")
def create_session(project_id: str, ep: str, body: SessionCreate, request: Request) -> dict[str, Any]:
    return _svc(request).create_session(project_id, ep, body)


@router.post("/projects/{project_id}/episodes/{ep}/n1/steps/{step}/submit")
def submit_step(
    project_id: str,
    ep: str,
    step: int,
    body: SubmitPayload,
    request: Request,
) -> dict[str, Any]:
    return _svc(request).submit_step(project_id, ep, step, body)


@router.put("/projects/{project_id}/episodes/{ep}/n1/draft")
def put_draft(project_id: str, ep: str, body: DraftPayload, request: Request) -> dict[str, Any]:
    return _svc(request).put_draft(project_id, ep, body)


@router.get("/projects/{project_id}/episodes/{ep}/n1")
def get_n1(
    project_id: str,
    ep: str,
    request: Request,
    consumer: str = "authoring",
) -> dict[str, Any]:
    if consumer not in {"authoring", "downstream"}:
        raise AppError(400, "invalid_consumer", "consumer must be authoring or downstream")
    return _svc(request).get_n1(project_id, ep, consumer=consumer)


@router.get("/projects/{project_id}/episodes/{ep}/n1/final")
def get_n1_final(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    """Downstream read. 409 when locked=false."""
    return _svc(request).get_n1(project_id, ep, consumer="downstream")


@router.get("/projects/{project_id}/episodes/{ep}/gates")
def get_gates(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    view = _svc(request).get_n1(project_id, ep, consumer="authoring")
    return {"episode": ep, "gates": [view["gate"]], "next_edges": view.get("next_edges") or []}


@router.post("/projects/{project_id}/episodes/{ep}/gates/g1/confirm")
async def confirm_g1(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    raw = await request.json()
    if not isinstance(raw, dict):
        raise AppError(400, "invalid_body", "JSON object required")
    body = GateConfirm.model_validate(raw)
    return _svc(request).confirm_g1(project_id, ep, body, raw_payload=raw)


@router.api_route(
    "/projects/{project_id}/episodes/{ep}/n1/lock",
    methods=["GET", "POST", "PUT"],
)
def n1_lock_removed(project_id: str, ep: str) -> JSONResponse:
    """ENG sketched n1/lock; BRIEF makes gates/g1/confirm the sole lock."""
    return JSONResponse(
        status_code=404,
        content={
            "error": "lock_path_removed",
            "message": "Use POST .../gates/g1/confirm only. No n1/lock, no force_pass.",
            "confirm_path": f"/api/v0/projects/{project_id}/episodes/{ep}/gates/g1/confirm",
        },
    )
