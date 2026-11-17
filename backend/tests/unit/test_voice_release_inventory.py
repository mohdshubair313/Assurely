"""Configuration cannot manufacture runtime observation or external acceptance."""

import json
import uuid

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.core.config import Settings
from app.voice.release import release_status


def configured() -> Settings:
    return Settings(
        _env_file=None,
        environment="staging",
        auth_provider="clerk",
        auth_issuer="https://synthetic.clerk.accounts.dev",
        voice_development_enabled=True,
        voice_test_subjects=[str(uuid.uuid4())],
        vaani_agent_id=str(uuid.uuid4()),
        vaani_api_key=SecretStr("synthetic-api-secret-never-export"),
        vaani_staging_base_url="https://voice.example.invalid",
        vaani_byol_token=SecretStr("synthetic-byol-credential" * 3),
        vaani_webhook_secret=SecretStr("synthetic-webhook-credential" * 3),
        voice_token_encryption_key=SecretStr(Fernet.generate_key().decode()),
        vaani_dev_agent_reviewed=True,
        vaani_byol_enabled=True,
        vaani_ingress_enabled=True,
        vaani_dispatch_enabled=True,
    )


def test_all_configuration_still_requires_external_acceptance_and_unobserved_runtime():
    settings = configured()
    result = release_status(settings)
    assert all(result["configuration_checks"].values())
    assert result["development_readiness"] == "awaiting_external_acceptance"
    assert result["runtime_observations"]["application_schema"] == "not_checked"
    assert result["runtime_observations"]["genuine_audio_delivery"] == "not_verified"
    assert result["customer_calls_enabled"] is result["paid_billing_enabled"] is False
    assert settings.vaani_api_key.get_secret_value() not in json.dumps(result)
    assert settings.vaani_byol_token.get_secret_value() not in json.dumps(result)
    assert settings.voice_token_encryption_key.get_secret_value() not in json.dumps(result)


@pytest.mark.parametrize(
    "origin",
    [
        "http://voice.invalid",
        "https://user:password@voice.invalid",
        "https://voice.invalid?token=private",
        "https://voice.invalid/call",
        "https://voice.invalid:broken",
    ],
)
def test_invalid_private_or_non_origin_url_cannot_pass_configuration(origin):
    settings = configured()
    settings.vaani_staging_base_url = origin
    result = release_status(settings)
    assert result["development_readiness"] == "configuration_incomplete"
    assert result["configuration_checks"]["https_origin_shape"] is False
    assert origin not in json.dumps(result)


def test_disabled_gate_wins_even_if_all_other_configuration_exists():
    settings = configured()
    settings.voice_development_enabled = False
    assert release_status(settings)["development_readiness"] == "disabled"


def test_bad_identifier_and_missing_keys_never_imply_owned_agent_or_authentication():
    settings = configured()
    settings.vaani_agent_id = "not-an-owned-uuid"
    settings.vaani_api_key = SecretStr("")
    result = release_status(settings)
    assert result["configuration_checks"]["agent_identifier_uuid_shape"] is False
    assert result["configuration_checks"]["api_key_present"] is False
    assert result["runtime_observations"]["current_provider_authentication"] == "not_checked"
