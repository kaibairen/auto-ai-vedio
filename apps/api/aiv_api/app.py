from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError

from aiv_n1 import __version__
from aiv_n1.config import Settings
from aiv_n1.errors import AppError
from aiv_n1.service import N1Service
from aiv_api.routes import router

def _workbench_dir(settings: Settings) -> Path:
    return settings.repo_root / "apps" / "workbench"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(
        title="aiv N1 口播定稿",
        version=__version__,
        description=(
            "N1 runtime. Sole lock: POST .../gates/g1/confirm. "
            "ForcePass=never. Path B step b3_skipped is a source-defect ack. "
            "provisional:P-STACK=Python; P-D1/P-D2/P-D7/P-PROJ."
        ),
    )
    app.state.settings = settings
    app.state.service = N1Service(settings)

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_envelope())

    @app.exception_handler(RequestValidationError)
    async def _pyd(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"ok": False, "error": {"code": "validation", "message": "invalid body", "details": exc.errors()}},
        )

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "node": "N1", "version": __version__, "provisional": ["P-D1", "P-D2", "P-D7", "P-PROJ", "P-STACK"]}

    wb = _workbench_dir(settings)
    if wb.is_dir():
        app.mount("/workbench", StaticFiles(directory=str(wb)), name="workbench")

        @app.get("/")
        def wizard_root() -> FileResponse:
            return FileResponse(wb / "index.html")

        @app.get("/projects/{project_id}/episodes/{ep}/n1")
        def wizard_route(project_id: str, ep: str) -> FileResponse:
            return FileResponse(wb / "index.html")

    app.include_router(router)
    return app
