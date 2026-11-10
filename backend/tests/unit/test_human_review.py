"""Human-review requests have no customer-supplied approval authority."""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.v1 import human_review as api
from app.core import security
from app.core.config import Settings
from app.core.security import require_authenticated_user_id
from app.db import human_review as store
from app.db.schema import compatible_schema


@pytest.mark.parametrize("field", ["role", "user_id", "assigned_advisor", "approved", "reason"])
def test_request_command_rejects_authority_and_unnecessary_sensitive_text(field):
    with pytest.raises(ValidationError):
        store.RequestCommand.model_validate({"request_key": str(uuid.uuid4()), field: "injected"})


@pytest.mark.parametrize("value", [None, "", "not-a-uuid", 1])
def test_request_requires_uuid_idempotency_key(value):
    with pytest.raises(ValidationError):
        store.RequestCommand.model_validate({"request_key": value})


def test_additive_schema_readiness_requires_new_revision_only_for_enabled_feature():
    settings = Settings(_env_file=None)
    assert settings.human_review_requests_enabled is False
    assert compatible_schema("015_human_review_requests", settings)
    assert compatible_schema("014_voice_managed", settings)
    assert compatible_schema("013_vaani_backend", settings)
    settings.human_review_requests_enabled = True
    assert compatible_schema("015_human_review_requests", settings)
    assert not compatible_schema("014_voice_managed", settings)
    assert not compatible_schema("013_vaani_backend", settings)
    settings.human_review_requests_enabled = False
    settings.voice_development_enabled = True
    assert compatible_schema("014_voice_managed", settings)
    assert not compatible_schema("013_vaani_backend", settings)


def test_http_authentication_and_closed_body_validation(monkeypatch):
    settings = Settings(
        _env_file=None,
        auth_provider="clerk",
        auth_issuer="https://synthetic.clerk.accounts.dev",
        auth_jwks_url="https://synthetic.clerk.accounts.dev/.well-known/jwks.json",
        auth_authorized_parties=["https://assurely.example.test"],
        environment="staging",
        human_review_requests_enabled=True,
    )
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    monkeypatch.setattr(store, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(api.router, prefix="/v1")
    endpoint = f"/v1/sessions/{uuid.uuid4()}/human-review"
    with TestClient(app) as client:
        assert client.get(endpoint).status_code == 401
        assert client.post(endpoint, json={"request_key": str(uuid.uuid4())}).status_code == 401
        app.dependency_overrides[require_authenticated_user_id] = lambda: uuid.uuid4()
        invalid_bodies = [
            {"request_key": str(uuid.uuid4()), "approved": True},
            {"request_key": str(uuid.uuid4()), "user_id": str(uuid.uuid4())},
            {"request_key": str(uuid.uuid4()), "assigned_advisor": str(uuid.uuid4())},
            {},
            {"request_key": "invalid"},
        ]
        for body in invalid_bodies:
            assert client.post(endpoint, json=body).status_code == 422
        duplicate = f'{{"request_key":"{uuid.uuid4()}","request_key":"{uuid.uuid4()}"}}'
        assert (
            client.post(
                endpoint, content=duplicate, headers={"Content-Type": "application/json"}
            ).status_code
            == 422
        )
        assert (
            client.post(
                endpoint, content="x" * 17_000, headers={"Content-Type": "application/json"}
            ).status_code
            == 413
        )
