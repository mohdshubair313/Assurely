"""LLM provider clients — Groq, Gemini Flash, and OpenRouter.

Wraps each provider's API behind a common interface so the
fallback_chain can swap between them transparently.

Per HLD/LLD § 1 (free LLM providers):
  - Groq:       fast/cheap for conversational turns, classification
  - Gemini Flash: long-context reasoning for compare_verify and guardrail
  - OpenRouter:  automatic fallback when Groq/Gemini rate-limit mid-session

All calls go through httpx async clients with structured results and timing.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Base exception for provider failures."""

    def __init__(self, provider: str, message: str, status_code: int | None = None, is_rate_limit: bool = False):
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.status_code = status_code
        self.is_rate_limit = is_rate_limit


class ProviderRateLimitError(ProviderError):
    """Raised when a provider returns 429 Too Many Requests."""

    def __init__(self, provider: str, message: str = "Rate limit reached"):
        super().__init__(provider=provider, message=message, status_code=429, is_rate_limit=True)


class ProviderAuthError(ProviderError):
    """Raised when API key is missing or invalid (401/403)."""

    def __init__(self, provider: str, message: str = "Authentication failed / invalid API key"):
        super().__init__(provider=provider, message=message, status_code=401)


class ProviderUnavailableError(ProviderError):
    """Raised when provider is down, times out, or returns 5xx."""


@dataclass
class LLMResult:
    """Standardized response from any LLM provider."""

    content: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    finish_reason: str = "stop"


class BaseProvider:
    """Base class for LLM providers."""

    name: str = "base"

    async def call(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout: float = 30.0,
    ) -> LLMResult:
        raise NotImplementedError


class GroqProvider(BaseProvider):
    """Groq API provider (OpenAI-compatible)."""

    name: str = "groq"
    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str | None = None, default_model: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.groq_api_key
        self.default_model = default_model or settings.groq_model

    async def call(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout: float = 30.0,
    ) -> LLMResult:
        if not self.api_key:
            raise ProviderAuthError(self.name, "GROQ_API_KEY is not configured")

        chosen_model = model or self.default_model
        payload = {
            "model": chosen_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self.BASE_URL, json=payload, headers=headers)
        except httpx.TimeoutException as e:
            raise ProviderUnavailableError(self.name, f"Request timed out after {timeout}s: {e}")
        except httpx.RequestError as e:
            raise ProviderUnavailableError(self.name, f"Connection error: {e}")

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if response.status_code == 429:
            raise ProviderRateLimitError(self.name, response.text)
        if response.status_code in (401, 403):
            raise ProviderAuthError(self.name, response.text)
        if response.status_code >= 500:
            raise ProviderUnavailableError(self.name, f"Server error {response.status_code}: {response.text}")
        if response.status_code != 200:
            raise ProviderError(self.name, f"Unexpected response {response.status_code}: {response.text}")

        data = response.json()
        choice = data["choices"][0]
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

        return LLMResult(
            content=choice["message"]["content"] or "",
            provider=self.name,
            model=data.get("model", chosen_model),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            finish_reason=choice.get("finish_reason", "stop"),
        )


class GeminiProvider(BaseProvider):
    """Google Gemini API provider using the OpenAI-compatible endpoint."""

    name: str = "gemini"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

    def __init__(self, api_key: str | None = None, default_model: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.gemini_api_key
        self.default_model = default_model or settings.gemini_model

    async def call(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout: float = 30.0,
    ) -> LLMResult:
        if not self.api_key:
            raise ProviderAuthError(self.name, "GEMINI_API_KEY is not configured")

        chosen_model = model or self.default_model
        payload = {
            "model": chosen_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self.BASE_URL, json=payload, headers=headers)
        except httpx.TimeoutException as e:
            raise ProviderUnavailableError(self.name, f"Request timed out after {timeout}s: {e}")
        except httpx.RequestError as e:
            raise ProviderUnavailableError(self.name, f"Connection error: {e}")

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if response.status_code == 429:
            raise ProviderRateLimitError(self.name, response.text)
        if response.status_code in (401, 403):
            raise ProviderAuthError(self.name, response.text)
        if response.status_code >= 500:
            raise ProviderUnavailableError(self.name, f"Server error {response.status_code}: {response.text}")
        if response.status_code != 200:
            raise ProviderError(self.name, f"Unexpected response {response.status_code}: {response.text}")

        data = response.json()
        choice = data["choices"][0]
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

        return LLMResult(
            content=choice["message"]["content"] or "",
            provider=self.name,
            model=data.get("model", chosen_model),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            finish_reason=choice.get("finish_reason", "stop"),
        )


class OpenRouterProvider(BaseProvider):
    """OpenRouter API provider (rotating free models fallback)."""

    name: str = "openrouter"
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str | None = None, fallback_models: list[str] | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.openrouter_api_key
        if fallback_models:
            self.fallback_models = fallback_models
        else:
            self.fallback_models = [m.strip() for m in settings.openrouter_models.split(",") if m.strip()]

    async def call(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout: float = 30.0,
    ) -> LLMResult:
        if not self.api_key:
            raise ProviderAuthError(self.name, "OPENROUTER_API_KEY is not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://insurance-ai.internal",
            "X-Title": "InsuranceAI Advisor Platform",
        }

        # If a specific model is requested, try it. Otherwise try each fallback model in sequence.
        candidate_models = [model] if model else self.fallback_models
        last_exception: Exception | None = None

        for cand in candidate_models:
            if not cand:
                continue
            payload = {
                "model": cand,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            start_time = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(self.BASE_URL, json=payload, headers=headers)
            except (httpx.TimeoutException, httpx.RequestError) as e:
                logger.warning("OpenRouter model %s connection failed: %s. Trying next...", cand, e)
                last_exception = ProviderUnavailableError(self.name, f"Connection to {cand} failed: {e}")
                continue

            latency_ms = (time.perf_counter() - start_time) * 1000.0

            if response.status_code == 429:
                logger.warning("OpenRouter model %s rate-limited (429). Trying next fallback model...", cand)
                last_exception = ProviderRateLimitError(self.name, response.text)
                continue

            if response.status_code in (401, 403):
                raise ProviderAuthError(self.name, response.text)

            if response.status_code >= 500:
                logger.warning("OpenRouter model %s 5xx error: %s. Trying next...", cand, response.status_code)
                last_exception = ProviderUnavailableError(self.name, f"Model {cand} 5xx: {response.text}")
                continue

            if response.status_code != 200:
                last_exception = ProviderError(self.name, f"Model {cand} status {response.status_code}: {response.text}")
                continue

            data = response.json()
            choice = data["choices"][0]
            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

            return LLMResult(
                content=choice["message"]["content"] or "",
                provider=self.name,
                model=data.get("model", cand),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_ms=latency_ms,
                finish_reason=choice.get("finish_reason", "stop"),
            )

        if last_exception:
            raise last_exception
        raise ProviderUnavailableError(self.name, "All candidate OpenRouter models failed")
