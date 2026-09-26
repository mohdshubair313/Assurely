"""Application configuration via environment variables.

Uses Pydantic BaseSettings to load and validate:
  - DATABASE_URL (Postgres async connection string)
  - REDIS_URL
  - CHROMA_HOST / CHROMA_PORT
  - LLM provider API keys (GROQ_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY)
  - ENVIRONMENT (development | staging | production)
  - LOG_LEVEL
  - Rate-limit budgets (tokens per session, calls per minute)
  - LANGFUSE_* credentials for observability

All secrets are read from environment variables or a .env file.
No defaults for secrets in production.
"""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration — all values from env vars or .env file."""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # ── Environment ─────────────────────────────────────────────────────
    environment: str = Field(default="development", description="development | staging | production")
    log_level: str = Field(default="info", description="Logging level")

    # ── Database ────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://insurance:insurance_dev@localhost:5432/insurance_db",
        description="Postgres async connection string",
    )

    # ── Redis ───────────────────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection string",
    )

    # ── Chroma ──────────────────────────────────────────────────────────
    chroma_host: str = Field(default="localhost", description="ChromaDB host")
    chroma_port: int = Field(default=8100, description="ChromaDB port")

    # ── LLM Provider API Keys ───────────────────────────────────────────
    # All optional for local dev; must be set in staging/production.
    groq_api_key: str = Field(default="", description="Groq API key")
    gemini_api_key: str = Field(default="", description="Google Gemini API key")
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")

    # ── LLM Models ──────────────────────────────────────────────────────
    groq_model: str = Field(default="llama-3.3-70b-versatile", description="Default Groq model")
    gemini_model: str = Field(default="gemini-2.5-flash", description="Default Gemini model")
    openrouter_models: str = Field(
        default="meta-llama/llama-3.3-70b-instruct:free,google/gemma-2-9b-it:free,qwen/qwen-2.5-72b-instruct:free",
        description="Comma-separated OpenRouter fallback model IDs (free tier rotates)",
    )

    # ── Rate Limiting ───────────────────────────────────────────────────
    rate_limit_tokens_per_session: int = Field(
        default=50_000, description="Max tokens per session across all LLM calls"
    )
    rate_limit_calls_per_minute: int = Field(
        default=20, description="Max LLM calls per minute per session"
    )

    # ── Langfuse (observability) ────────────────────────────────────────
    langfuse_public_key: str = Field(default="", description="Langfuse public key")
    langfuse_secret_key: str = Field(default="", description="Langfuse secret key")
    langfuse_host: str = Field(default="http://localhost:3000", description="Langfuse host URL")

    # ── Timeouts ────────────────────────────────────────────────────────
    llm_timeout_seconds: float = Field(default=30.0, description="LLM call timeout")
    llm_max_retries: int = Field(default=2, description="Max retries per provider before fallback")

    # Advisor queue: unset until an operator configures an authorized receiver.
    advisor_webhook_url: str = ""
    advisor_webhook_token: SecretStr = SecretStr("")
    advisor_webhook_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    advisor_webhook_max_attempts: int = Field(default=3, ge=1, le=5)
    advisor_webhook_retry_delay_seconds: float = Field(default=0.25, ge=0, le=5)


def get_settings() -> Settings:
    """Return the application settings (cached by Pydantic internally)."""
    return Settings()
