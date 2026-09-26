"""Session + platform-wide rate limiter.

Per LLD § 9: the rate limiter is a decorator/middleware around the shared
``llm_call()`` fallback function, keyed by ``session_id`` — NOT a graph node.

Responsibilities:
  - Track token + call budget per session (Redis counters with TTL, with in-memory fallback).
  - Enforce platform-wide limits and per-session cost ceiling.
  - Return a clear "budget exhausted" signal when limits are hit.
  - Expose metrics (calls remaining, tokens remaining) for observability.
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class RateLimitExceededError(Exception):
    """Raised when a session or the platform exceeds rate or token limits."""

    def __init__(self, message: str, retry_after_seconds: int = 60, reason: str = "rate_limit_exceeded"):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
        self.reason = reason


class InMemoryRateLimiterBackend:
    """In-memory fallback when Redis is not reachable or during local testing."""

    def __init__(self) -> None:
        self.call_windows: dict[str, list[float]] = {}
        self.session_tokens: dict[str, int] = {}

    def record_call(self, session_id: str, max_calls_per_minute: int) -> bool:
        now = time.time()
        window_start = now - 60.0
        calls = [t for t in self.call_windows.get(session_id, []) if t > window_start]
        if len(calls) >= max_calls_per_minute:
            self.call_windows[session_id] = calls
            return False
        calls.append(now)
        self.call_windows[session_id] = calls
        return True

    def record_tokens(self, session_id: str, tokens: int, max_tokens: int) -> tuple[bool, int]:
        current = self.session_tokens.get(session_id, 0) + tokens
        self.session_tokens[session_id] = current
        if current > max_tokens:
            return False, current
        return True, current

    def get_stats(self, session_id: str, max_calls: int, max_tokens: int) -> dict[str, int]:
        now = time.time()
        window_start = now - 60.0
        calls = [t for t in self.call_windows.get(session_id, []) if t > window_start]
        used_tokens = self.session_tokens.get(session_id, 0)
        return {
            "calls_used_minute": len(calls),
            "calls_remaining_minute": max(0, max_calls - len(calls)),
            "tokens_used_session": used_tokens,
            "tokens_remaining_session": max(0, max_tokens - used_tokens),
        }

    def reset(self, session_id: str | None = None) -> None:
        if session_id:
            self.call_windows.pop(session_id, None)
            self.session_tokens.pop(session_id, None)
        else:
            self.call_windows.clear()
            self.session_tokens.clear()


class RateLimiter:
    """Session and platform rate limiter."""

    def __init__(self) -> None:
        self._memory_backend = InMemoryRateLimiterBackend()
        self._settings = get_settings()
        self._last_redis_check: float = 0.0
        self._redis_available: bool = False

    async def _get_redis(self) -> Any:
        now = time.time()
        # If we checked within the last 10 seconds and Redis wasn't available, skip
        if not self._redis_available and (now - self._last_redis_check) < 10.0:
            return None

        self._last_redis_check = now
        try:
            from app.cache.redis_client import get_redis_client

            client = await get_redis_client()
            if client is not None:
                await client.ping()
                self._redis_available = True
                return client
        except Exception:
            self._redis_available = False
        return None


    async def check_call_limit(self, session_id: str) -> None:
        """Check if session is within calls-per-minute limit."""
        if not session_id:
            return

        settings = get_settings()
        max_cpm = settings.rate_limit_calls_per_minute

        redis = await self._get_redis()
        if redis:
            try:
                now = int(time.time())
                key = f"rate:calls:{session_id}:{now // 60}"
                count = await redis.incr(key)
                if count == 1:
                    await redis.expire(key, 90)
                if count > max_cpm:
                    logger.warning("Rate limit exceeded for session %s: %d > %d", session_id, count, max_cpm)
                    raise RateLimitExceededError(
                        f"Rate limit exceeded: max {max_cpm} calls per minute.",
                        retry_after_seconds=60 - (now % 60),
                        reason="calls_per_minute_exceeded",
                    )
                return
            except RateLimitExceededError:
                raise
            except Exception as e:
                logger.debug("Redis rate-limit check failed, falling back to memory: %s", e)

        # In-memory fallback
        allowed = self._memory_backend.record_call(session_id, max_cpm)
        if not allowed:
            raise RateLimitExceededError(
                f"Rate limit exceeded: max {max_cpm} calls per minute.",
                retry_after_seconds=30,
                reason="calls_per_minute_exceeded",
            )

    async def record_tokens(self, session_id: str, tokens: int) -> None:
        """Record tokens consumed and check if session exceeds total token budget."""
        if not session_id or tokens <= 0:
            return

        settings = get_settings()
        max_tokens = settings.rate_limit_tokens_per_session

        redis = await self._get_redis()
        if redis:
            try:
                key = f"rate:tokens:{session_id}"
                total = await redis.incrby(key, tokens)
                # Keep session token counter for 24h
                await redis.expire(key, 86400)
                if total > max_tokens:
                    logger.warning("Token budget exceeded for session %s: %d > %d", session_id, total, max_tokens)
                    raise RateLimitExceededError(
                        f"Session token budget exhausted: {total} > {max_tokens}.",
                        retry_after_seconds=3600,
                        reason="session_tokens_exceeded",
                    )
                return
            except RateLimitExceededError:
                raise
            except Exception as e:
                logger.debug("Redis token recording failed, falling back to memory: %s", e)

        allowed, current = self._memory_backend.record_tokens(session_id, tokens, max_tokens)
        if not allowed:
            raise RateLimitExceededError(
                f"Session token budget exhausted: {current} > {max_tokens}.",
                retry_after_seconds=3600,
                reason="session_tokens_exceeded",
            )

    async def get_stats(self, session_id: str) -> dict[str, int]:
        """Return usage stats for the session."""
        settings = get_settings()
        return self._memory_backend.get_stats(
            session_id,
            settings.rate_limit_calls_per_minute,
            settings.rate_limit_tokens_per_session,
        )


_global_rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _global_rate_limiter


def rate_limited(func: Callable) -> Callable:
    """Decorator for llm_call to enforce rate limiting by session_id."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        session_id = kwargs.get("session_id")
        limiter = get_rate_limiter()

        if session_id:
            await limiter.check_call_limit(session_id)

        result = await func(*args, **kwargs)

        if session_id and hasattr(result, "total_tokens") and result.total_tokens:
            await limiter.record_tokens(session_id, result.total_tokens)

        return result

    return wrapper
