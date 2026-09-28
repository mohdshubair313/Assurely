"""FastAPI application factory.

Mounts all API routers (v1) and configures middleware.
Entrypoint for uvicorn: ``uvicorn app.main:app``.

Responsibilities:
  - Create the FastAPI instance with metadata (title, version, docs URL).
  - Include the v1 API router.
  - Expose health check endpoint GET /health.
  - Register startup/shutdown lifecycle hooks for Postgres, Redis, and Chroma.
  - Attach CORS and logging middleware.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.v1.router import api_v1_router
from app.cache.redis_client import close_redis_client
from app.core.config import get_settings
from app.core.correlation import correlation_scope
from app.core.exception_log import LoggingBoundary
from app.core.tracing import flush_langfuse

logger = logging.getLogger(__name__)


class RequestErrorBoundary:
    """Correlate all HTTP failures without logging URLs, headers or bodies."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracked_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        with correlation_scope():
            try:
                await self.app(scope, receive, tracked_send)
            except Exception:
                logger.exception("Unhandled API failure")
                if not started:
                    response = JSONResponse(
                        {"detail": "Unable to process this request."}, status_code=500
                    )
                    await response(scope, receive, send)
                else:
                    raise


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown lifecycle hooks."""
    settings = get_settings()
    boundary = LoggingBoundary(settings)
    app.state.exception_sink = boundary.sink

    async def retention_loop() -> None:
        while True:
            await asyncio.sleep(settings.exception_log_cleanup_seconds)
            try:
                await asyncio.to_thread(boundary.sink.prune)
            except Exception:
                boundary.sink.failed = True
                logger.exception("Exception retention failed")

    cleanup = asyncio.create_task(retention_loop())
    try:
        logger.info("Application started")
        yield
    finally:
        cleanup.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup
        try:
            await close_redis_client()
            await asyncio.to_thread(flush_langfuse)
        finally:
            boundary.close()


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="InsuranceAI Advisory Platform API",
        description="Multi-agent health insurance advisory platform for India (Phase 0 Skeleton).",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestErrorBoundary)

    # Mount v1 router
    app.include_router(api_v1_router)

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Liveness / readiness health probe."""
        sink = getattr(app.state, "exception_sink", None)
        if sink is not None and sink.failed:
            from fastapi import HTTPException

            raise HTTPException(status_code=503, detail="Restricted diagnostics unavailable.")
        return {
            "status": "healthy",
            "environment": settings.environment,
            "version": "0.1.0",
        }

    return app


app = create_app()
