"""Bounded dependency probes. Never return connection details or approval data."""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.cache.redis_client import get_redis_client
from app.db.session import AsyncSessionLocal


async def dependencies_ready() -> bool:
    async def database_ready() -> bool:
        async with AsyncSessionLocal() as db:
            version = await db.scalar(text("SELECT version_num FROM alembic_version"))
            return bool(version == "010_clerk_identity")

    async def redis_ready() -> bool:
        redis = await get_redis_client()
        return redis is not None and bool(await redis.ping())

    try:
        async with asyncio.timeout(5):
            results = await asyncio.gather(database_ready(), redis_ready(), return_exceptions=True)
            return all(result is True for result in results)
    except Exception:
        return False
