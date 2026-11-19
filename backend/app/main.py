import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.routes import router
from app.db import DiagramStore
from app.errors import STATUS_BY_CODE, AppError
from app.jobs.manager import JobManager
from app.models import DiagramRecord

FRONTEND_ORIGIN = os.environ.get("DIAGRAMMA_FRONTEND_ORIGIN", "http://localhost:5173")
_DEFAULT_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
FRONTEND_DIST = Path(os.environ.get("DIAGRAMMA_FRONTEND_DIST", _DEFAULT_DIST))


def _error(code: str, message: str, status: int | None = None) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message}},
        status_code=status or STATUS_BY_CODE.get(code, 500),
    )


def create_app(jobs: JobManager | None = None, store: DiagramStore | None = None) -> FastAPI:
    manager = jobs or JobManager()
    store = store or DiagramStore()

    def finalize(result: dict) -> dict:
        diagram = result.pop("diagram", None)
        if diagram is not None:
            result["diagramId"] = store.add(DiagramRecord(**diagram)).id
        return result

    manager.finalize = manager.finalize or finalize

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        manager.start()
        yield
        manager.stop()

    app = FastAPI(title="Diagramma", version=__version__, lifespan=lifespan)
    app.state.jobs = manager
    app.state.store = store
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[FRONTEND_ORIGIN, "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error(exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error("VALIDATION_ERROR", "Invalid request body.")

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Unknown routes, wrong methods, etc.: same envelope as every other error.
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        message = {404: "Not found.", 405: "Method not allowed."}.get(
            exc.status_code, "Request failed."
        )
        return _error(code, message, exc.status_code)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        return _error("INTERNAL_ERROR", "Unexpected server error.", 500)  # details stay in the log

    app.include_router(router)
    # Run mode: serve the built frontend if present (mounted last so /api wins).
    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    return app


app = create_app()
