"""Run explicit pytest selections without dotenv or inherited service credentials.

Usage: python -m tests.run_offline tests/unit/test_input_validate.py -q
Service boundaries must still be mocked by tests; this launcher does not make
real integrations into unit tests.
"""

from __future__ import annotations

import os
import sys

import pytest
from pydantic_settings.sources import DotEnvSettingsSource

from app.core.config import Settings


def main() -> int:
    Settings.model_config["env_file"] = None
    for name in (
        "GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY",
        "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY",
        "ADVISOR_WEBHOOK_URL", "ADVISOR_WEBHOOK_TOKEN",
        "AUTH_ISSUER", "AUTH_AUDIENCE", "AUTH_JWKS_URL",
    ):
        os.environ[name] = ""
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://offline:offline@127.0.0.1:1/offline"
    os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"
    os.environ["CHROMA_HOST"] = "127.0.0.1"
    os.environ["CHROMA_PORT"] = "1"

    original_read = DotEnvSettingsSource._read_env_files

    def no_dotenv(self: DotEnvSettingsSource) -> dict[str, str | None]:
        if self.env_file:
            raise AssertionError("Offline checks must not access dotenv files")
        return {}

    DotEnvSettingsSource._read_env_files = no_dotenv
    try:
        return int(pytest.main(sys.argv[1:]))
    finally:
        DotEnvSettingsSource._read_env_files = original_read


if __name__ == "__main__":
    raise SystemExit(main())
