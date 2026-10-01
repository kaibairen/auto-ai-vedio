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
    SidecarAddCharacterRequest,
)
from aiv_drama.service import DramaService
from aiv_drama.validate import reject_dual_skill, reject_force_keys
from aiv_drama_n2.models import (
    StoryboardGenerateRequest,
    StoryboardReorderRequest,
    StoryboardResetRequest,
    StoryboardWrite,
)
from aiv_drama_n2.validate import reject_force_keys_n2, reject_prompt_fields
from aiv_drama_n3.models import (
    LibrarySceneWrite,
    N3AttachRequest,
    N3ForkRequest,
    N3MaterializeRequest,
    N3PromoteRequest,
    N3ThickenRequest,
)
from aiv_drama_n3.validate import reject_force_keys_n3, reject_image_gen_n3
from aiv_drama_n4.models import N4AssembleRequest, N4ValidateRequest
from aiv_drama_n4.validate import reject_force_keys_n4

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


async def _raw_n2(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(data, dict):
        raise AppError(400, "validation", "JSON object required")
    reject_force_keys_n2(data)
    reject_prompt_fields(data)
    return data


async def _raw_n3(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(data, dict):
        raise AppError(400, "validation", "JSON object required")
    reject_force_keys_n3(data)
    reject_image_gen_n3(data)
    return data


async def _raw_n4(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(data, dict):
        raise AppError(400, "validation", "JSON object required")
    reject_force_keys_n4(data)
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


@router.post("/projects/{project_id}/episodes/{ep}/drama/cast/sidecar-add")
async def sidecar_add_character(
    project_id: str,
    ep: str,
    body: SidecarAddCharacterRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    """O2 sidecar: add CHAR without unlocking G1b or rewriting locked outline."""
    raw = await _raw(request)
    return _svc(request).sidecar_add_character(project_id, ep, body, raw=raw, idempotency_key=idempotency_key)


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


@router.get("/drama/error-catalog")
def error_catalog(request: Request) -> dict[str, Any]:
    """018d bilingual ErrorCode / GAP-COPY catalog. docs≠PASS."""
    return _svc(request).error_catalog()


@router.post("/projects/{project_id}/episodes/{ep}/drama/copy-contract/evaluate")
async def evaluate_copy_contract(
    project_id: str,
    ep: str,
    request: Request,
) -> dict[str, Any]:
    """018d GAP-COPY overlay: tool_profile / duration chips / ready_for_n4."""
    raw = await _raw(request)
    return _svc(request).evaluate_copy_contract(project_id, ep, raw)


@router.get("/projects/{project_id}/episodes/{ep}/drama/downstream")
def get_downstream(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    """D-N2 consumer read. 409 upstream_unlocked if G1b not locked. Does not start D-N2."""
    return _svc(request).get_downstream(project_id, ep)


@router.get("/projects/{project_id}/episodes/{ep}/drama/storyboard")
def get_storyboard(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    return _svc(request).get_storyboard(project_id, ep)


@router.put("/projects/{project_id}/episodes/{ep}/drama/storyboard")
async def put_storyboard(
    project_id: str,
    ep: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    raw = await _raw_n2(request)
    body = StoryboardWrite.model_validate(raw)
    return _svc(request).put_storyboard(
        project_id, ep, body, raw=raw, if_match=if_match, idempotency_key=idempotency_key
    )


@router.post("/projects/{project_id}/episodes/{ep}/drama/storyboard/generate")
async def generate_storyboard(
    project_id: str,
    ep: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    raw = await _raw_n2(request)
    body = StoryboardGenerateRequest.model_validate(raw) if raw else StoryboardGenerateRequest()
    return _svc(request).generate_storyboard(project_id, ep, body, raw=raw, idempotency_key=idempotency_key)


@router.post("/projects/{project_id}/episodes/{ep}/drama/storyboard/validate")
async def validate_storyboard(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    raw = await _raw_n2(request)
    return _svc(request).validate_storyboard(project_id, ep, raw=raw)


@router.post("/projects/{project_id}/episodes/{ep}/drama/storyboard/reorder")
async def reorder_storyboard(
    project_id: str,
    ep: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    raw = await _raw_n2(request)
    body = StoryboardReorderRequest.model_validate(raw)
    return _svc(request).reorder_storyboard(
        project_id, ep, body, raw=raw, if_match=if_match, idempotency_key=idempotency_key
    )


@router.post("/projects/{project_id}/episodes/{ep}/drama/storyboard/reset")
async def reset_storyboard(
    project_id: str,
    ep: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    raw = await _raw_n2(request)
    body = StoryboardResetRequest.model_validate(raw) if raw else StoryboardResetRequest()
    return _svc(request).reset_storyboard(project_id, ep, body, raw=raw, idempotency_key=idempotency_key)


@router.get("/projects/{project_id}/episodes/{ep}/gates/g2")
def get_gate_g2(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    return _svc(request).get_gate_g2(project_id, ep)


@router.post("/projects/{project_id}/episodes/{ep}/gates/g2/confirm")
async def confirm_gate_g2(
    project_id: str,
    ep: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_actor: str | None = Header(default=None, alias="X-Actor"),
) -> dict[str, Any]:
    raw = await _raw_n2(request)
    if x_actor and not raw.get("actor"):
        raw = {**raw, "actor": x_actor}
    return _svc(request).confirm_gate_g2(project_id, ep, raw, idempotency_key=idempotency_key)


@router.get("/projects/{project_id}/library")
def get_library(project_id: str, request: Request) -> dict[str, Any]:
    return _svc(request).get_library(project_id)


@router.get("/projects/{project_id}/library/policy")
def get_library_policy(project_id: str, request: Request) -> dict[str, Any]:
    return _svc(request).get_library_policy(project_id)


@router.put("/projects/{project_id}/library/scenes/{scene_id}")
def put_library_scene(
    project_id: str,
    scene_id: str,
    body: LibrarySceneWrite,
    request: Request,
) -> dict[str, Any]:
    return _svc(request).put_library_scene(project_id, scene_id, body)


@router.get("/projects/{project_id}/episodes/{ep}/drama/n3")
def get_n3(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    return _svc(request).get_n3(project_id, ep)


@router.get("/projects/{project_id}/episodes/{ep}/drama/n3/cards")
def get_n3_cards(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    return _svc(request).get_n3_cards(project_id, ep)


@router.post("/projects/{project_id}/episodes/{ep}/drama/n3/cards/materialize")
async def materialize_n3_cards(
    project_id: str,
    ep: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    raw = await _raw_n3(request)
    body = N3MaterializeRequest.model_validate(raw) if raw else N3MaterializeRequest()
    return _svc(request).materialize_n3_cards(project_id, ep, body, raw=raw, idempotency_key=idempotency_key)


@router.post("/projects/{project_id}/episodes/{ep}/drama/n3/cards/thicken")
async def thicken_n3_cards(
    project_id: str,
    ep: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    raw = await _raw_n3(request)
    body = N3ThickenRequest.model_validate(raw) if raw else N3ThickenRequest()
    return _svc(request).thicken_n3_cards(project_id, ep, body, raw=raw, idempotency_key=idempotency_key)


@router.get("/projects/{project_id}/episodes/{ep}/drama/n3/storyboard-crop")
def get_n3_crop(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    return _svc(request).get_n3_crop(project_id, ep)


@router.post("/projects/{project_id}/episodes/{ep}/drama/n3/cards/attach")
async def attach_n3_card(
    project_id: str,
    ep: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    raw = await _raw_n3(request)
    body = N3AttachRequest.model_validate(raw)
    return _svc(request).attach_n3_card(project_id, ep, body, raw=raw, idempotency_key=idempotency_key)


@router.post("/projects/{project_id}/episodes/{ep}/drama/n3/cards/promote")
async def promote_n3_card(
    project_id: str,
    ep: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    raw = await _raw_n3(request)
    body = N3PromoteRequest.model_validate(raw)
    return _svc(request).promote_n3_card(project_id, ep, body, raw=raw, idempotency_key=idempotency_key)


@router.post("/projects/{project_id}/episodes/{ep}/drama/n3/cards/fork")
async def fork_n3_card(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    raw = await _raw_n3(request)
    body = N3ForkRequest.model_validate(raw)
    return _svc(request).fork_n3_card(project_id, ep, body, raw=raw)


@router.get("/projects/{project_id}/episodes/{ep}/gates/g3")
def get_gate_g3(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    return _svc(request).get_gate_g3(project_id, ep)


@router.post("/projects/{project_id}/episodes/{ep}/gates/g3/confirm")
async def confirm_gate_g3(
    project_id: str,
    ep: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_actor: str | None = Header(default=None, alias="X-Actor"),
) -> dict[str, Any]:
    raw = await _raw_n3(request)
    if x_actor and not raw.get("actor"):
        raw = {**raw, "actor": x_actor}
    return _svc(request).confirm_gate_g3(project_id, ep, raw, idempotency_key=idempotency_key)


@router.get("/projects/{project_id}/episodes/{ep}/drama/n4-consumer")
def get_dn4_consumer(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    """D-N4 consumer read. 409 if G3 unlocked. started=true after successful assemble."""
    return _svc(request).get_dn4_consumer(project_id, ep)


@router.get("/projects/{project_id}/episodes/{ep}/drama/n4")
def get_n4(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    return _svc(request).get_n4(project_id, ep)


@router.get("/projects/{project_id}/episodes/{ep}/drama/n4/status")
def get_n4_status(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    return _svc(request).get_n4_status(project_id, ep)


@router.post("/projects/{project_id}/episodes/{ep}/drama/n4/validate")
async def validate_n4(project_id: str, ep: str, request: Request) -> dict[str, Any]:
    raw = await _raw_n4(request)
    body = N4ValidateRequest.model_validate(raw) if raw else N4ValidateRequest()
    return _svc(request).validate_n4(project_id, ep, body, raw=raw)


@router.post("/projects/{project_id}/episodes/{ep}/drama/n4/assemble")
async def assemble_n4(
    project_id: str,
    ep: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    raw = await _raw_n4(request)
    body = N4AssembleRequest.model_validate(raw) if raw else N4AssembleRequest()
    return _svc(request).assemble_n4(project_id, ep, body, raw=raw, idempotency_key=idempotency_key)


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


def _bare_n2_isolated() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "ok": False,
            "error": {
                "code": "not_found",
                "message": "bare N2 / koubo n2 is not served; use D-N2 /drama/storyboard and gates/g2",
                "details": {"pipeline_profile": "drama", "nodes": ["D-N2"], "gate": "g2"},
            },
        },
    )


@router.api_route("/projects/{project_id}/episodes/{ep}/n2/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/projects/{project_id}/episodes/{ep}/nodes/n2/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/projects/{project_id}/episodes/{ep}/n2", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/projects/{project_id}/episodes/{ep}/nodes/n2", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def bare_n2_paths_isolated(project_id: str, ep: str, rest: str = "") -> JSONResponse:
    return _bare_n2_isolated()


def _bare_n3_isolated() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "ok": False,
            "error": {
                "code": "not_found",
                "message": "bare N3 is not served; use D-N3 /drama/n3 and gates/g3",
                "details": {"pipeline_profile": "drama", "nodes": ["D-N3"], "gate": "g3"},
            },
        },
    )


@router.api_route("/projects/{project_id}/episodes/{ep}/n3/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/projects/{project_id}/episodes/{ep}/nodes/n3/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/projects/{project_id}/episodes/{ep}/n3", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/projects/{project_id}/episodes/{ep}/nodes/n3", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def bare_n3_paths_isolated(project_id: str, ep: str, rest: str = "") -> JSONResponse:
    return _bare_n3_isolated()


def _bare_n4_isolated() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "ok": False,
            "error": {
                "code": "not_found",
                "message": "bare N4 is not served; use D-N4 /drama/n4 and /drama/n4-consumer",
                "details": {
                    "pipeline_profile": "drama",
                    "nodes": ["D-N4"],
                    "use": ["/drama/n4", "/drama/n4/assemble", "/drama/n4/validate", "/drama/n4/status"],
                },
            },
        },
    )


@router.api_route("/projects/{project_id}/episodes/{ep}/n4/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/projects/{project_id}/episodes/{ep}/nodes/n4/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/projects/{project_id}/episodes/{ep}/n4", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/projects/{project_id}/episodes/{ep}/nodes/n4", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def bare_n4_paths_isolated(project_id: str, ep: str, rest: str = "") -> JSONResponse:
    return _bare_n4_isolated()
