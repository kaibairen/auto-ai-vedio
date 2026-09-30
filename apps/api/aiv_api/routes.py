from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from aiv_drama.errors import AppError
from aiv_drama.models import (
    AttachRequest,
    CastWrite,
    ClearDramaIntentRequest,
    ConfirmDramaIntentRequest,
    DetachRequest,
    DramaBriefWrite,
    EpisodeCreate,
    EpisodePatch,
    LibraryCharacterWrite,
    OutlineGenerateRequest,
    OutlineResetRequest,
    OutlineWrite,
    ProjectCreate,
    ProjectPatch,
)
from aiv_drama.service import DramaService
from aiv_drama.validate import reject_dual_skill, reject_force_keys

router = APIRouter(prefix="/api/v0")


def _svc(request: Request) -> DramaService:
    return request.app.state.service


async def _raw(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(data, dict):
        raise AppError(400, "validation", "JSON object required")
    reject_force_keys(data)
    return data


@router.post("/projects")
async def create_project(
    body: ProjectCreate,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    return _svc(request).create_project(body, idempotency_key=idempotency_key)


@router.get("/projects/{project_id}")
def get_project(project_id: str, request: Request) -> dict[str, Any]:
    return _svc(request).get_project(project_id)


@router.patch("/projects/{project_id}")
async def patch_project(
    project_id: str,
    body: ProjectPatch,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    return _svc(request).patch_project(project_id, body, if_match=if_match, idempotency_key=idempotency_key)


@router.delete("/projects/{project_id}")
def archive_project(project_id: str, request: Request) -> dict[str, Any]:
    return _svc(request).archive_project(project_id)


@router.put("/projects/{project_id}/library/characters/{character_id}")
def put_library_character(
    project_id: str,
    character_id: str,
    body: LibraryCharacterWrite,
    request: Request,
) -> dict[str, Any]:
    """Dogfood seed for D12 attach. Not list/search (those paths are absent from OpenAPI)."""
    return _svc(request).put_library_character(project_id, character_id, body)


@router.post("/projects/{project_id}/episodes")
async def create_episode(
    project_id: str,
    body: EpisodeCreate,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    return _svc(request).create_episode(project_id, body, idempotency_key=idempotency_key)


@router.get("/projects/{project_id}/episodes/{ep}")
def get_episode(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    return _svc(request).get_episode(project_id, ep)


@router.patch("/projects/{project_id}/episodes/{ep}")
async def patch_episode(
    project_id: str,
    ep: str,
    body: EpisodePatch,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    return _svc(request).patch_episode(project_id, ep, body, if_match=if_match, idempotency_key=idempotency_key)


@router.delete("/projects/{project_id}/episodes/{ep}")
def abandon_episode(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    return _svc(request).abandon_episode(project_id, ep)


@router.get("/projects/{project_id}/episodes/{ep}/drama/brief")
def get_brief(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    return _svc(request).get_brief(project_id, ep)


@router.put("/projects/{project_id}/episodes/{ep}/drama/brief")
async def put_brief(
    project_id: str,
    ep: str,
    body: DramaBriefWrite,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    raw = await _raw(request)
    return _svc(request).put_brief(
        project_id, ep, body, raw=raw, if_match=if_match, idempotency_key=idempotency_key
    )


@router.get("/projects/{project_id}/episodes/{ep}/drama/intent")
def get_intent(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    return _svc(request).get_intent(project_id, ep)


@router.post("/projects/{project_id}/episodes/{ep}/drama/intent/check")
async def check_intent(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    raw = await _raw(request)
    return _svc(request).check_intent(project_id, ep, raw=raw)


@router.post("/projects/{project_id}/episodes/{ep}/drama/intent/confirm")
async def confirm_intent(
    project_id: str,
    ep: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    raw = await _raw(request)
    body = ConfirmDramaIntentRequest.model_validate(raw) if raw else ConfirmDramaIntentRequest()
    return _svc(request).confirm_intent(project_id, ep, body, raw=raw, idempotency_key=idempotency_key)


@router.post("/projects/{project_id}/episodes/{ep}/drama/intent/clear")
async def clear_intent(
    project_id: str,
    ep: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    raw = await _raw(request)
    body = ClearDramaIntentRequest.model_validate(raw) if raw else ClearDramaIntentRequest()
    return _svc(request).clear_intent(project_id, ep, body, raw=raw, idempotency_key=idempotency_key)


@router.get("/projects/{project_id}/episodes/{ep}/drama/outline")
def get_outline(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    return _svc(request).get_outline(project_id, ep)


@router.post("/projects/{project_id}/episodes/{ep}/drama/outline")
async def generate_outline(
    project_id: str,
    ep: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    raw = await _raw(request)
    reject_dual_skill(raw)
    body = OutlineGenerateRequest.model_validate(raw) if raw else OutlineGenerateRequest()
    return _svc(request).generate_outline(project_id, ep, body, raw=raw, idempotency_key=idempotency_key)


@router.put("/projects/{project_id}/episodes/{ep}/drama/outline")
async def put_outline(
    project_id: str,
    ep: str,
    body: OutlineWrite,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    raw = await _raw(request)
    return _svc(request).put_outline(
        project_id, ep, body, raw=raw, if_match=if_match, idempotency_key=idempotency_key
    )


@router.post("/projects/{project_id}/episodes/{ep}/drama/outline/reset")
async def reset_outline(
    project_id: str,
    ep: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    raw = await _raw(request)
    body = OutlineResetRequest.model_validate(raw) if raw else OutlineResetRequest()
    return _svc(request).reset_outline(project_id, ep, body, raw=raw, idempotency_key=idempotency_key)


@router.get("/projects/{project_id}/episodes/{ep}/drama/cast")
def get_cast(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    return _svc(request).get_cast(project_id, ep)


@router.put("/projects/{project_id}/episodes/{ep}/drama/cast")
async def put_cast(
    project_id: str,
    ep: str,
    body: CastWrite,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    raw = await _raw(request)
    return _svc(request).put_cast(project_id, ep, body, raw=raw, if_match=if_match, idempotency_key=idempotency_key)


@router.post("/projects/{project_id}/episodes/{ep}/drama/cast/attach")
async def attach_character(
    project_id: str,
    ep: str,
    body: AttachRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    raw = await _raw(request)
    return _svc(request).attach_character(project_id, ep, body, raw=raw, idempotency_key=idempotency_key)


@router.post("/projects/{project_id}/episodes/{ep}/drama/cast/detach")
async def detach_character(
    project_id: str,
    ep: str,
    body: DetachRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    raw = await _raw(request)
    return _svc(request).detach_character(project_id, ep, body, raw=raw, idempotency_key=idempotency_key)


@router.get("/projects/{project_id}/episodes/{ep}/gates/g1b")
def get_gate(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    return _svc(request).get_gate(project_id, ep)


@router.post("/projects/{project_id}/episodes/{ep}/gates/g1b/confirm")
async def confirm_gate(
    project_id: str,
    ep: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_actor: str | None = Header(default=None, alias="X-Actor"),
) -> dict[str, Any]:
    raw = await _raw(request)
    if x_actor and not raw.get("actor"):
        raw = {**raw, "actor": x_actor}
    return _svc(request).confirm_gate(project_id, ep, raw, idempotency_key=idempotency_key)


@router.get("/projects/{project_id}/episodes/{ep}/drama/downstream")
def get_downstream(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    """D-N2 consumer read. 409 upstream_unlocked if G1b not locked. Does not start D-N2."""
    return _svc(request).get_downstream(project_id, ep)


def _koubo_isolated() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "ok": False,
            "error": {
                "code": "not_found",
                "message": "koubo-N1 is not served on this runtime; use D-N0 / D-N1 and gates/g1b",
                "details": {"pipeline_profile": "drama", "nodes": ["D-N0", "D-N1"], "gate": "g1b"},
            },
        },
    )


@router.api_route("/projects/{project_id}/episodes/{ep}/n1/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/projects/{project_id}/episodes/{ep}/nodes/n1/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/projects/{project_id}/episodes/{ep}/gates/g1/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/projects/{project_id}/episodes/{ep}/gates/g1", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/projects/{project_id}/episodes/{ep}/n1", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/projects/{project_id}/episodes/{ep}/nodes/n1", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def koubo_paths_isolated(project_id: str, ep: str, rest: str = "") -> JSONResponse:
    return _koubo_isolated()
