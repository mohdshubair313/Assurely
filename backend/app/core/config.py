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

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration — all values from env vars or .env file."""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # ── Environment ─────────────────────────────────────────────────────
    environment: str = Field(
        default="development", description="development | staging | production"
    )
    log_level: str = Field(default="info", description="Logging level")
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    # Explicitly restrict the whole local API while it is exposed through a test tunnel.
    tunnel_ingress_only: bool = False

    # Mandatory restricted diagnostics. Linux file permissions are verified at startup.
    exception_log_dir: str = "/var/log/insuranceai/private"
    exception_log_retention_hours: int = Field(default=168, ge=1, le=720)
    exception_log_max_records: int = Field(default=1000, ge=1, le=100000)
    exception_log_cleanup_seconds: int = Field(default=60, ge=1, le=3600)

    # Trusted identity provider. All three must be configured before any
    # profile-memory or consent action can use a bearer token.
    auth_issuer: str = ""
    auth_audience: str = ""
    auth_jwks_url: str = ""
    clerk_publishable_key: str = ""
    clerk_secret_key: SecretStr = SecretStr("")
    # Explicit migration switch; never infer the provider from untrusted claims.
    auth_provider: str = "legacy_oidc"
    auth_authorized_parties: list[str] = Field(default_factory=list)
    admin_subjects: list[str] = Field(default_factory=list)
    # Operator-designated test identities can never exercise privileged roles.
    auth_test_subjects: list[str] = Field(default_factory=list)
    # Server-to-server ingress control, independent of customer/operator JWT roles.
    backend_gateway_token: SecretStr = SecretStr("")

    # Explicit operator-managed subjects under AUTH_ISSUER; no client role claim.
    # Empty disables policy-review APIs. Never populated from customer profile data.
    policy_reviewer_subjects: list[str] = Field(default_factory=list)
    # Independent authority for publication/revocation; empty disables publication.
    policy_publisher_subjects: list[str] = Field(default_factory=list)
    advisor_subjects: list[str] = Field(default_factory=list)
    # Separate from voice subscriptions; does not authorize delivery or dispatch.
    human_review_requests_enabled: bool = False

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
    groq_model: str = Field(default="openai/gpt-oss-20b", description="Default Groq model")
    gemini_model: str = Field(default="gemini-3.8-flash", description="Default Gemini model")
    openrouter_models: str = Field(
        default="openrouter/free",
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
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com",
        validation_alias=AliasChoices("LANGFUSE_BASE_URL", "LANGFUSE_HOST"),
        description="Langfuse base URL",
    )

    # ── Timeouts ────────────────────────────────────────────────────────
    llm_timeout_seconds: float = Field(default=30.0, description="LLM call timeout")
    llm_max_retries: int = Field(default=2, description="Max retries per provider before fallback")

    # Advisor queue: unset until an operator configures an authorized receiver.
    advisor_webhook_url: str = ""
    advisor_webhook_token: SecretStr = SecretStr("")
    advisor_webhook_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    advisor_webhook_max_attempts: int = Field(default=3, ge=1, le=5)
    advisor_webhook_retry_delay_seconds: float = Field(default=0.25, ge=0, le=5)

    # Voice stays closed unless explicitly enabled. The mock provider can only
    # issue non-billable test entitlements to these server-allowlisted UUIDs.
    voice_provider: str = Field(default="disabled", pattern="^(disabled|mock|vaani)$")
    voice_recovery_interval_seconds: int = Field(default=5, ge=1, le=300)
    voice_test_subjects: list[str] = Field(default_factory=list)
    voice_test_allowance_minutes: int = Field(default=15, ge=1, le=600)
    voice_max_call_seconds: int = Field(default=300, ge=30, le=1800)
    voice_max_concurrent_calls: int = Field(default=1, ge=1, le=5)
    vaani_api_key: SecretStr = SecretStr("")
    vaani_agent_id: str = ""
    vaani_webhook_secret: SecretStr = SecretStr("")
    vaani_byol_token: SecretStr = SecretStr("")
    vaani_dispatch_enabled: bool = False
    vaani_ingress_enabled: bool = False
    vaani_byol_enabled: bool = False
    vaani_dev_agent_reviewed: bool = False
    vaani_staging_base_url: str = ""
    # Independent opt-ins; never inferred from credentials or a browser request.
    voice_development_enabled: bool = False
    voice_tools_enabled: bool = False
    voice_case_binding_enabled: bool = False
    voice_byol_evidence_enabled: bool = False
    voice_billing_test_enabled: bool = False
    voice_funded_test_enabled: bool = False
    voice_token_encryption_key: SecretStr = SecretStr("")
    voice_summary_retention_hours: int = Field(default=24, ge=1, le=168)
    razorpay_test_key_id: str = ""
    razorpay_test_key_secret: SecretStr = SecretStr("")
    razorpay_test_webhook_secret: SecretStr = SecretStr("")
    voice_test_plan_id: str = ""
    voice_test_plan_seconds: int = Field(default=0, ge=0, le=360000)


def get_settings() -> Settings:
    """Return the application settings (cached by Pydantic internally)."""
    return Settings()
