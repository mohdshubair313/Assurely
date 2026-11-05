"""Configuration checks expose gate states, never secret values or approval."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.ops.preflight import configuration_checks, report


def test_defaults_cannot_pass_release_configuration():
    checks = configuration_checks(Settings(_env_file=None,
        database_url="postgresql+asyncpg://insurance:insurance_dev@localhost:5432/insurance_db"))
    assert not checks["identity_configured"]
    assert not checks["explicit_operator_roles"]
    assert not checks["advisor_destination_configured"]
    assert not checks["database_password_not_development_default"]


@pytest.mark.asyncio
async def test_report_does_not_expose_configured_secrets_or_grant_release():
    settings = Settings(_env_file=None, groq_api_key="synthetic-secret-token")
    with patch("app.ops.preflight.get_settings", return_value=settings), patch(
        "app.ops.preflight.database_checks", AsyncMock(return_value={"application_schema": False}),
    ):
        result = await report(True)
    assert result["database_checked"] and not result["configuration_passed"]
    assert not result["production_release_authorized"]
    assert "synthetic-secret-token" not in json.dumps(result)


@pytest.mark.parametrize("roles", [["invalid-uuid"], []])
def test_invalid_or_missing_role_ids_never_pass(roles):
    checks = configuration_checks(Settings(_env_file=None, policy_reviewer_subjects=roles))
    assert not checks["explicit_operator_roles"]


def test_wildcard_origin_and_shared_review_publication_identity_fail():
    actor = "00000000-0000-4000-8000-000000000123"
    checks = configuration_checks(Settings(_env_file=None, cors_origins=["*"],
        policy_reviewer_subjects=[actor], policy_publisher_subjects=[actor],
        advisor_subjects=[actor]))
    assert not checks["separate_review_and_publication_roles"]
    assert not checks["explicit_browser_origins"]
