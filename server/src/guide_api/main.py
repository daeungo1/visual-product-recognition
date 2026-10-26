"""FastAPI entry point: `uvicorn guide_api.main:app --app-dir src --host 0.0.0.0`."""

import logging
import os
import sqlite3
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from guide_api.catalog import DEMO_GUIDE, get_guide
from guide_api.models import AdvanceEvent, AiRequest, Catalog, Guide, SessionState, StartSession
from guide_api.store import Store

MAX_BODY_BYTES = 8192
MAX_CLOUD_BODY_BYTES = 2_800_000


class BodyLimit:
    """Bound buffered JSON payloads even when Content-Length is absent or incorrect."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            limit = MAX_CLOUD_BODY_BYTES if scope["path"].startswith("/v1/") else MAX_BODY_BYTES
            if len(body) > limit:
                response = JSONResponse({"detail": "Request body exceeds limit."}, status_code=413)
                await response(scope, receive, send)
                return
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def create_app(database: Path | None = None, *, mode: str | None = None, cloud=None) -> FastAPI:
    """Create an explicit local or cloud instance; never silently change storage modes."""
    mode = mode or os.getenv("VISUAL_GUIDE_MODE", "local")
    if mode not in {"local", "cloud"}:
        raise ValueError("VISUAL_GUIDE_MODE must be local or cloud.")
    store = Store(database or Path(os.getenv("GUIDE_DATABASE", "data/guide.sqlite3")))
    initialization_lock = threading.Lock()
    last_initialization = float("-inf")

    def initialize_cloud(instance):
        nonlocal last_initialization
        with initialization_lock:
            if instance.state.cloud is not None or time.monotonic() - last_initialization < 5:
                return
            last_initialization = time.monotonic()
            try:
                from guide_api.azure_adapters import build_cloud_service

                instance.state.cloud = build_cloud_service()
            except (ImportError, ValueError, HTTPException) as error:
                logging.getLogger(__name__).warning(
                    "Cloud initialization failed error_type=%s",
                    type(error).__name__,
                )
                instance.state.cloud_error_status = (
                    error.status_code if isinstance(error, HTTPException) else 503
                )

    @asynccontextmanager
    async def lifespan(instance: FastAPI):
        if mode == "local":
            store.initialize()
        elif instance.state.cloud is None:
            await run_in_threadpool(initialize_cloud, instance)
        try:
            yield
        finally:
            if mode == "cloud" and cloud is None and instance.state.cloud is not None:
                instance.state.cloud.close()

    application = FastAPI(title=f"Visual Guide ({mode})", lifespan=lifespan)
    application.state.cloud = cloud
    application.state.cloud_error_status = 503
    origins = os.getenv(
        "GUIDE_CORS_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173",
    ).split(",")
    if any(origin.strip() == "*" for origin in origins):
        raise ValueError("Use explicit local CORS origins, never a wildcard.")
    application.add_middleware(BodyLimit)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in origins if origin.strip()],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @application.exception_handler(sqlite3.Error)
    async def database_error(_, __):
        return JSONResponse({"detail": "Local database unavailable."}, status_code=503)

    @application.exception_handler(RequestValidationError)
    async def validation_error(_, error):
        # Pydantic's default errors include raw input, including pairing codes and images.
        return JSONResponse(
            {
                "detail": [
                    {
                        "loc": [
                            part if isinstance(part, int) else str(part)[:80]
                            for part in item["loc"][:8]
                        ],
                        "type": item["type"],
                        "msg": item["msg"][:200],
                    }
                    for item in error.errors()[:12]
                ]
            },
            status_code=422,
        )

    @application.get("/healthz")
    def health():
        return {"status": "ok"}

    @application.get("/readyz")
    def ready():
        if mode == "cloud":
            initialize_cloud(application)
            if application.state.cloud is None:
                raise HTTPException(
                    application.state.cloud_error_status,
                    "Cloud configuration or dependencies unavailable.",
                )
            try:
                return application.state.cloud.ready()
            except HTTPException as error:
                if error.status_code == 429:
                    raise HTTPException(503, "Cloud dependency check is busy.") from error
                raise
        if not store.ready():
            return JSONResponse(
                {"status": "not_ready", "dependency": "local_sqlite"}, status_code=503
            )
        return {"status": "ready", "storage": "local_sqlite", "cloud_ai": "unconfigured"}

    if mode == "cloud":
        from guide_api.cloud_routes import router

        application.include_router(router)
        return application

    @application.get("/catalog", response_model=Catalog)
    def catalog():
        return Catalog(
            guides=[DEMO_GUIDE],
            notice="Synthetic target only. Samsung assets and production AI are unregistered.",
        )

    @application.get("/guides/{guide_id}", response_model=Guide)
    def guide(guide_id: str):
        return get_guide(guide_id)

    @application.get("/models/{model_id}")
    def model(model_id: str):
        if model_id != DEMO_GUIDE.target_id:
            raise HTTPException(404, "Model not registered; no real Samsung assets are installed.")
        return {"id": model_id, "demo": True, "kind": "synthetic_reference", "production_ai": False}

    @application.post("/sessions", status_code=201, response_model=SessionState)
    def start(body: StartSession):
        return store.start(body.guide_id)

    @application.get("/sessions/{session_id}", response_model=SessionState)
    def session(session_id: str):
        return store.get(session_id)

    @application.post("/sessions/{session_id}/events", response_model=SessionState)
    def advance(session_id: str, body: AdvanceEvent):
        return store.advance(session_id, body)

    @application.post("/ai/recognize", status_code=503)
    @application.post("/ai/verify", status_code=503)
    def unavailable_ai(body: AiRequest):
        raise HTTPException(
            503,
            "Production AI is unconfigured. No real product assets or cloud clients are installed. "
            "The on-device synthetic demo is separate; no recognition result was generated.",
        )

    return application


app = create_app()
