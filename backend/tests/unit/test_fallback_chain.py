"""Unit tests for the LLM fallback chain and rate limiter."""

import pytest
from unittest.mock import AsyncMock, patch

from app.core.rate_limiter import RateLimiter, RateLimitExceededError, rate_limited
from app.llm.fallback_chain import llm_call, get_providers, AllProvidersFailedError
from app.llm.providers import (
    GroqProvider,
    GeminiProvider,
    OpenRouterProvider,
    LLMResult,
    ProviderRateLimitError,
    ProviderUnavailableError,
)


@pytest.mark.asyncio
async def test_get_providers_order() -> None:
    """Verify task_type determines correct provider priority."""
    general_providers = get_providers("general")
    assert isinstance(general_providers[0], GroqProvider)
    assert isinstance(general_providers[1], GeminiProvider)
    assert isinstance(general_providers[2], OpenRouterProvider)

    compliance_providers = get_providers("compare_verify")
    assert isinstance(compliance_providers[0], GeminiProvider)
    assert isinstance(compliance_providers[1], GroqProvider)


@pytest.mark.asyncio
async def test_llm_call_mock_response() -> None:
    """Verify mock_response parameter works offline without API keys."""
    res = await llm_call(
        messages=[{"role": "user", "content": "hello"}],
        mock_response="Hello, how can I help you?",
        session_id="test-session-1",
    )
    assert isinstance(res, LLMResult)
    assert res.content == "Hello, how can I help you?"
    assert res.provider == "mock"
    assert res.total_tokens > 0


@pytest.mark.asyncio
async def test_fallback_when_primary_rate_limited() -> None:
    """Verify that when Groq is rate-limited (429), it falls through to Gemini."""
    mock_groq_call = AsyncMock(side_effect=ProviderRateLimitError("groq", "Rate limit hit"))
    mock_gemini_call = AsyncMock(
        return_value=LLMResult(
            content="Response from Gemini fallback",
            provider="gemini",
            model="gemini-2.5-flash",
            prompt_tokens=15,
            completion_tokens=20,
            total_tokens=35,
        )
    )

    with patch.object(GroqProvider, "call", mock_groq_call), \
         patch.object(GeminiProvider, "call", mock_gemini_call), \
         patch("app.llm.fallback_chain.get_settings") as mock_settings:

        # Configure settings to have both API keys and 0 retries for fast test
        mock_settings.return_value.groq_api_key = "gsk_test"
        mock_settings.return_value.gemini_api_key = "gem_test"
        mock_settings.return_value.openrouter_api_key = "or_test"
        mock_settings.return_value.llm_max_retries = 0
        mock_settings.return_value.llm_timeout_seconds = 5.0
        mock_settings.return_value.rate_limit_calls_per_minute = 100
        mock_settings.return_value.rate_limit_tokens_per_session = 50000

        result = await llm_call(
            messages=[{"role": "user", "content": "test fallback"}],
            task_type="general",
            session_id="fallback-test-session",
        )

        assert result.provider == "gemini"
        assert result.content == "Response from Gemini fallback"
        assert mock_groq_call.call_count == 1
        assert mock_gemini_call.call_count == 1


@pytest.mark.asyncio
async def test_rate_limiter_calls_per_minute() -> None:
    """Verify rate limiter throws RateLimitExceededError when CPM exceeded."""
    import uuid
    test_session = f"cpm-test-{uuid.uuid4()}"
    limiter = RateLimiter()
    limiter._memory_backend.reset(test_session)

    with patch("app.core.rate_limiter.get_settings") as mock_settings:
        mock_settings.return_value.rate_limit_calls_per_minute = 2
        mock_settings.return_value.rate_limit_tokens_per_session = 10000

        # 1st call: OK
        await limiter.check_call_limit(test_session)
        # 2nd call: OK
        await limiter.check_call_limit(test_session)
        # 3rd call: Exceeded!
        with pytest.raises(RateLimitExceededError) as exc_info:
            await limiter.check_call_limit(test_session)

        assert "calls per minute" in str(exc_info.value)


@pytest.mark.asyncio
async def test_rate_limiter_tokens_per_session() -> None:
    """Verify rate limiter throws RateLimitExceededError when token budget exceeded."""
    import uuid
    test_session = f"token-test-{uuid.uuid4()}"
    limiter = RateLimiter()
    limiter._memory_backend.reset(test_session)

    with patch("app.core.rate_limiter.get_settings") as mock_settings:
        mock_settings.return_value.rate_limit_tokens_per_session = 100
        mock_settings.return_value.rate_limit_calls_per_minute = 100

        # Consume 50 tokens: OK
        await limiter.record_tokens(test_session, 50)
        # Consume another 60 tokens: Exceeds 100 limit!
        with pytest.raises(RateLimitExceededError) as exc_info:
            await limiter.record_tokens(test_session, 60)

        assert "budget exhausted" in str(exc_info.value)

