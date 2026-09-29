from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from aiv import __version__
from aiv.api.routes import router
from aiv.config import Settings
from aiv.errors import AppError
from aiv.service import N1Service

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(
        title="aiv N1 口播定稿",
        version=__version__,
        description=(
            "Minimal N1 runtime. Gate lock is only POST .../gates/g1/confirm. "
            "ForcePass=never. Path B skips defective step 3."
        ),
    )
    app.state.settings = settings
    app.state.service = N1Service(settings)

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "node": "N1", "version": __version__}

    if WEB_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

        @app.get("/")
        def wizard() -> FileResponse:
            return FileResponse(WEB_DIR / "n1.html")

    app.include_router(router)
    return app
