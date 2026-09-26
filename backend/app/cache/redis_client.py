"""Redis client — session state cache and rate-limit counters.

Per HLD/LLD § 13 (data architecture):
  Session state (in-flight conversation) lives in Redis with TTL-based
  expiry. It's ephemeral, high read/write, and doesn't need durability.

Also provides the backing store for rate-limit counters
(token budget + call count per session_id, with TTL).

Connection is async via ``redis.asyncio``.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_redis_client: Any | None = None


async def get_redis_client() -> Any | None:
    """Return a singleton async Redis client instance, or None if unavailable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    settings = get_settings()
    try:
        import redis.asyncio as redis

        _redis_client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )
        return _redis_client
    except Exception as e:
        logger.warning("Could not connect to Redis at %s: %s", settings.redis_url, e)
        return None


async def close_redis_client() -> None:
    """Close the active Redis connection pool."""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.close()
        except Exception:
            pass
        _redis_client = None
