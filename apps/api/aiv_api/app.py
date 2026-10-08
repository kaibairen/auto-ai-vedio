from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from aiv_api.routes import router
from aiv_drama import __version__
from aiv_drama.config import Settings
from aiv_drama.copy_contract import lookup_messages
from aiv_drama.errors import AppError
from aiv_drama.service import DramaService
from aiv_drama.validate import FORCE_KEYS
from aiv_schema.models import GATE_G1B, GATE_G2, GATE_G3, NODE_DN0, NODE_DN1, NODE_DN2, NODE_DN3, NODE_DN4


def _workbench_dir(settings: Settings) -> Path:
    return settings.repo_root / "apps" / "workbench"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(
        title="AI Video · Drama D-N0 / D-N1 / D-N2 / D-N3 / D-N4",
        version=__version__,
        description=(
            "短剧 pipeline_profile=drama · D-N0 + D-N1（门 G1b）+ D-N2 分镜表（门 G2）+ D-N3 单元卡（门 G3）"
            " + D-N4 确定性按镜拼装。 "
            "ForcePass=never. Isolated from koubo-N1. docs≠PASS. Does not auto-open D-N5."
        ),
    )
    app.state.settings = settings
    app.state.service = DramaService(settings)

    @app.middleware("http")
    async def force_pass_guard(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method in {"POST", "PUT", "PATCH"}:
            body = await request.body()
            if body:
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    data = None
                if isinstance(data, dict):
                    path = request.url.path
                    if "/drama/n4" in path:
                        node, gate = NODE_DN4, GATE_G3
                    elif "/gates/g3" in path or "/drama/n3" in path:
                        node, gate = NODE_DN3, GATE_G3
                    elif "/gates/g2" in path or "/drama/storyboard" in path:
                        node, gate = NODE_DN2, GATE_G2
                    elif any(
                        part in path
                        for part in (
                            "/reviews",
                            "/open-items",
                            "/cost",
                            "/outputs",
                            "/rough-cuts",
                            "/subtitles",
                            "/audio/",
                            "/segments/",
                        )
                    ):
                        node, gate = "post", None
                    else:
                        node, gate = NODE_DN1, GATE_G1B
                    for key in FORCE_KEYS:
                        if key in data:
                            pair = lookup_messages("force_pass_forbidden") or {
                                "zh": "禁止强制通过（ForcePass=never）。",
                                "en": "ForcePass=never",
                            }
                            return JSONResponse(
                                status_code=400,
                                content={
                                    "ok": False,
                                    "error": {
                                        "code": "force_pass_forbidden",
                                        "message": pair["zh"],
                                        "messages": pair,
                                        "details": {"field": key, "node": node, "gate": gate},
                                    },
                                },
                            )
        return await call_next(request)

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_envelope())

    @app.exception_handler(RequestValidationError)
    async def _pyd(_: Request, exc: RequestValidationError) -> JSONResponse:
        pair = lookup_messages("validation") or {"zh": "请求校验失败。", "en": "validation"}
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "error": {
                    "code": "validation",
                    "message": pair["zh"],
                    "messages": pair,
                    "details": exc.errors(),
                },
            },
        )

    @app.get("/health")
    def health() -> dict:
        return {
            "ok": True,
            "pipeline_profile": "drama",
            "nodes": [NODE_DN0, NODE_DN1, NODE_DN2, NODE_DN3, NODE_DN4],
            "gate": GATE_G1B,
            "gates": [GATE_G1B, GATE_G2, GATE_G3],
            "version": __version__,
            "koubo_n1": False,
            "docs_pass": False,
            "auto_open_dn3": False,
            "auto_open_dn4": False,
        }

    wb = _workbench_dir(settings)
    if wb.is_dir():
        app.mount("/workbench/static", StaticFiles(directory=str(wb)), name="workbench")

        @app.get("/")
        @app.get("/workbench")
        @app.get("/workbench/")
        def wizard_root() -> FileResponse:
            return FileResponse(wb / "index.html")

        @app.get("/projects/{project_id}/episodes/{ep}/drama/brief")
        @app.get("/projects/{project_id}/episodes/{ep}/drama/outline")
        @app.get("/projects/{project_id}/episodes/{ep}/drama/intent")
        def wizard_routes(project_id: str, ep: str) -> FileResponse:
            return FileResponse(wb / "index.html")

    openapi_copy = settings.repo_root / "openapi" / "drama-n0n1.v0.yaml"
    openapi_n2 = settings.repo_root / "openapi" / "drama-n2.v0.yaml"
    openapi_n3 = settings.repo_root / "openapi" / "drama-n3.v0.yaml"
    openapi_n4 = settings.repo_root / "openapi" / "drama-n4.v0.yaml"
    openapi_post = settings.repo_root / "openapi" / "drama-post.v0.yaml"

    @app.get("/openapi/drama-n0n1.v0.yaml")
    def openapi_file() -> FileResponse:
        return FileResponse(openapi_copy, media_type="application/yaml")

    @app.get("/openapi/drama-n2.v0.yaml")
    def openapi_n2_file() -> FileResponse:
        return FileResponse(openapi_n2, media_type="application/yaml")

    @app.get("/openapi/drama-n3.v0.yaml")
    def openapi_n3_file() -> FileResponse:
        return FileResponse(openapi_n3, media_type="application/yaml")

    @app.get("/openapi/drama-n4.v0.yaml")
    def openapi_n4_file() -> FileResponse:
        return FileResponse(openapi_n4, media_type="application/yaml")

    @app.get("/openapi/drama-post.v0.yaml")
    def openapi_post_file() -> FileResponse:
        return FileResponse(openapi_post, media_type="application/yaml")

    app.include_router(router)
    return app
