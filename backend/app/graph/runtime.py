"""Durable graph lifecycle and issuer/session/turn checkpoint namespaces."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from sqlalchemy import select

from app.core.config import get_settings
from app.core.correlation import database_session_id
from app.db.connection_urls import checkpoint_conninfo
from app.db.policy_review_store import WorkflowError
from app.db.session import AsyncSessionLocal
from app.graph.build_graph import build_graph
from app.models.db.report_release import ReportHead


def turn_config(issuer: str, session_id: str, turn_id: Any) -> RunnableConfig:
    key = f"{issuer}\n{database_session_id(session_id)}\n{turn_id}"
    return {"configurable": {"thread_id": hashlib.sha256(key.encode()).hexdigest()}}


async def read_config(session_id: str, *, current_only: bool = False) -> RunnableConfig | None:
    settings = get_settings()
    if settings.environment == "development":
        return {"configurable": {"thread_id": session_id}}
    async with AsyncSessionLocal() as db:
        row = await db.scalar(select(ReportHead).where(
            ReportHead.issuer == settings.auth_issuer,
            ReportHead.session_id == database_session_id(session_id),
        ))
        if row is None or row.completed_turn_id is None:
            return None
        if current_only and (row.status != "complete" or row.completed_turn_id != row.turn_id):
            return None
        return turn_config(settings.auth_issuer, session_id, row.completed_turn_id)


@asynccontextmanager
async def durable_graph(*, setup: bool = False) -> AsyncIterator[Any]:
    # Imported lazily so development retains its explicitly in-memory workflow.
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg import AsyncConnection
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    async with AsyncConnectionPool[AsyncConnection[dict[str, Any]]](
        conninfo=checkpoint_conninfo(get_settings().database_url), min_size=1, max_size=10,
        check=AsyncConnectionPool.check_connection,
        timeout=15, kwargs={"autocommit": True, "row_factory": dict_row,
                            "prepare_threshold": 0}, open=False,
    ) as pool:
        await pool.wait(timeout=15)
        saver = AsyncPostgresSaver(pool, serde=JsonPlusSerializer(
            pickle_fallback=False, allowed_msgpack_modules=[],
        ))
        if setup:
            await saver.setup()
        # Startup never silently creates/migrates checkpoint tables.
        async with pool.connection() as conn, conn.cursor() as cursor:
            await cursor.execute("SELECT MAX(v) AS version FROM checkpoint_migrations")
            result = await cursor.fetchone()
            if not result or result["version"] != len(saver.MIGRATIONS) - 1:
                raise WorkflowError(503, "Checkpoint database setup is required.")
        yield build_graph(saver)
