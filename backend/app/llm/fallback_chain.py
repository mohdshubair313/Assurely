"""LLM fallback chain — retry/fallback wrapper with rate limiting.

Implements the single ``llm_call()`` interface that all graph nodes use.
Ordered fallback chain: Groq → Gemini Flash → OpenRouter free tier.

The rate_limiter decorator from ``app.core.rate_limiter`` attaches here,
gating every call by session_id token and call budget (LLD § 9).

Responsibilities:
  - Select primary provider based on task_type (Groq for general/intake, Gemini for long-context/guardrail).
  - On rate limit or transient error, retry with backoff, then fall through to next provider.
  - On OpenRouter, try rotating candidate free models.
  - Log provider swaps and latency for observability.
  - Return standardized LLMResult with content and usage metadata.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import get_settings
from app.core.rate_limiter import rate_limited
from app.llm.providers import (
    BaseProvider,
    GeminiProvider,
    GroqProvider,
    LLMResult,
    OpenRouterProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
)

logger = logging.getLogger(__name__)


class AllProvidersFailedError(Exception):
    """Raised when all LLM providers in the fallback chain fail."""

    def __init__(self, message: str, errors: list[dict[str, Any]]):
        super().__init__(message)
        self.errors = errors


def get_providers(task_type: str = "general", preferred_provider: str | None = None) -> list[BaseProvider]:
    """Return ordered list of providers for the given task.

    Task types:
      - "general", "intake", "router": Groq primary -> Gemini -> OpenRouter
      - "long_context", "compare_verify", "guardrail": Gemini primary -> Groq -> OpenRouter
    """
    settings = get_settings()

    groq = GroqProvider()
    gemini = GeminiProvider()
    openrouter = OpenRouterProvider()

    if preferred_provider:
        name_map = {"groq": groq, "gemini": gemini, "openrouter": openrouter}
        if preferred_provider in name_map:
            primary = name_map[preferred_provider]
            others = [p for p in [groq, gemini, openrouter] if p != primary]
            return [primary] + others

    if task_type in ("long_context", "compare_verify", "guardrail"):
        return [gemini, groq, openrouter]

    return [groq, gemini, openrouter]


@rate_limited
async def llm_call(
    messages: list[dict[str, str]],
    system_prompt: str | None = None,
    task_type: str = "general",
    session_id: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    preferred_provider: str | None = None,
    mock_response: str | None = None,
) -> LLMResult:
    """Execute an LLM call with automatic fallback and rate limiting.

    Args:
        messages: List of message dicts (e.g. [{"role": "user", "content": "..."}]).
        system_prompt: Optional system instructions prepended to messages.
        task_type: "general" | "intake" | "compare_verify" | "guardrail" | "long_context".
        session_id: Session ID for rate-limiting and audit tracking.
        temperature: Generation temperature (0.0 - 1.0).
        max_tokens: Maximum tokens in completion.
        preferred_provider: Force specific provider as primary ("groq"|"gemini"|"openrouter").
        mock_response: If provided, bypasses network calls and returns mock result (for offline testing).

    Returns:
        LLMResult with response content, provider/model used, and token stats.

    Raises:
        RateLimitExceededError: If session exceeds token or call limits.
        AllProvidersFailedError: If all providers in fallback chain fail.
    """
    if mock_response is not None:
        return LLMResult(
            content=mock_response,
            provider="mock",
            model="mock-model",
            prompt_tokens=10,
            completion_tokens=len(mock_response.split()),
            total_tokens=10 + len(mock_response.split()),
            latency_ms=1.0,
            finish_reason="stop",
        )

    formatted_messages = list(messages)
    if system_prompt:
        formatted_messages.insert(0, {"role": "system", "content": system_prompt})

    settings = get_settings()
    providers = get_providers(task_type, preferred_provider)
    max_retries = settings.llm_max_retries
    timeout = settings.llm_timeout_seconds

    attempt_errors: list[dict[str, Any]] = []

    for provider in providers:
        # Check if provider has credentials configured
        if isinstance(provider, GroqProvider) and not settings.groq_api_key:
            attempt_errors.append({"provider": provider.name, "error": "GROQ_API_KEY not set"})
            continue
        if isinstance(provider, GeminiProvider) and not settings.gemini_api_key:
            attempt_errors.append({"provider": provider.name, "error": "GEMINI_API_KEY not set"})
            continue
        if isinstance(provider, OpenRouterProvider) and not settings.openrouter_api_key:
            attempt_errors.append({"provider": provider.name, "error": "OPENROUTER_API_KEY not set"})
            continue

        for attempt in range(max_retries + 1):
            try:
                logger.info(
                    "Attempting LLM call with provider=%s attempt=%d/%d task_type=%s session=%s",
                    provider.name,
                    attempt + 1,
                    max_retries + 1,
                    task_type,
                    session_id,
                )
                result = await provider.call(
                    messages=formatted_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
                logger.info(
                    "LLM call succeeded: provider=%s model=%s tokens=%d latency=%.1fms",
                    result.provider,
                    result.model,
                    result.total_tokens,
                    result.latency_ms,
                )
                return result

            except ProviderRateLimitError as e:
                logger.warning(
                    "Provider %s rate-limited (attempt %d/%d): %s",
                    provider.name,
                    attempt + 1,
                    max_retries + 1,
                    e,
                )
                if attempt < max_retries:
                    backoff = 1.5 * (2**attempt)
                    await asyncio.sleep(backoff)
                else:
                    attempt_errors.append({"provider": provider.name, "error": str(e), "rate_limited": True})
                    break  # Try next provider in fallback chain

            except ProviderAuthError as e:
                logger.error("Provider %s auth error: %s. Skipping provider.", provider.name, e)
                attempt_errors.append({"provider": provider.name, "error": str(e), "auth_error": True})
                break  # Don't retry auth errors, proceed to next provider

            except ProviderError as e:
                logger.warning(
                    "Provider %s error (attempt %d/%d): %s",
                    provider.name,
                    attempt + 1,
                    max_retries + 1,
                    e,
                )
                if attempt < max_retries:
                    backoff = 1.0 * (2**attempt)
                    await asyncio.sleep(backoff)
                else:
                    attempt_errors.append({"provider": provider.name, "error": str(e)})
                    break

            except Exception as e:
                logger.exception("Unexpected error in provider %s: %s", provider.name, e)
                attempt_errors.append({"provider": provider.name, "error": str(e)})
                break

    # If all configured providers failed or no provider was configured
    err_summary = "; ".join(f"{e.get('provider')}: {e.get('error')}" for e in attempt_errors)
    msg = f"All LLM providers in the fallback chain failed: {err_summary}"
    logger.error(msg)
    raise AllProvidersFailedError(msg, attempt_errors)
