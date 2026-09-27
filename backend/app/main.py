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
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.cache.redis_client import close_redis_client
from app.core.config import get_settings
from app.core.tracing import flush_langfuse

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown lifecycle hooks."""
    settings = get_settings()
    logger.info("Starting InsuranceAI Advisory Backend in %s mode", settings.environment)
    yield
    logger.info("Shutting down InsuranceAI Advisory Backend")
    await close_redis_client()
    await asyncio.to_thread(flush_langfuse)


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

    # Mount v1 router
    app.include_router(api_v1_router)

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Liveness / readiness health probe."""
        return {
            "status": "healthy",
            "environment": settings.environment,
            "version": "0.1.0",
        }

    return app


app = create_app()
