"""Signed identity and operator authorization guard every policy-review endpoint."""

import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import policy_reviews as api
from app.core import policy_review_auth, security

SUBJECT = uuid.UUID("00000000-0000-4000-8000-000000000123")
ISSUER = "https://identity.example.test/"
DIGEST = "a" * 64


@pytest.fixture
def setup(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = SimpleNamespace(
        auth_issuer=ISSUER,
        auth_audience="policy-test",
        auth_jwks_url=ISSUER + "jwks",
        policy_reviewer_subjects=[str(SUBJECT)],
    )
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    monkeypatch.setattr(policy_review_auth, "get_settings", lambda: settings)
    monkeypatch.setattr(
        security,
        "_jwks_client",
        lambda _: SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key()),
        ),
    )
    app = FastAPI()
    app.include_router(api.router, prefix="/v1")

    async def forbidden_db():
        raise AssertionError("Unauthorized request reached storage")
        yield  # pragma: no cover

    app.dependency_overrides[api.review_db] = forbidden_db
    return app, TestClient(app), key, settings


def token(key, **changes):
    now = int(time.time())
    claims = {
        "sub": str(SUBJECT),
        "iss": ISSUER,
        "aud": "policy-test",
        "iat": now,
        "exp": now + 300,
        **changes,
    }
    return {"Authorization": "Bearer " + jwt.encode(claims, key, algorithm="RS256")}


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("POST", "/drafts", {}),
        ("GET", "/drafts/" + DIGEST, None),
        ("POST", "/drafts/" + DIGEST + "/reviews", {}),
        ("POST", "/drafts/" + DIGEST + "/import-checks", {}),
    ],
)
def test_every_endpoint_rejects_anonymous_access(setup, method, path, body):
    _, client, _, _ = setup
    response = client.request(method, "/v1/policy-reviews" + path, json=body)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "change",
    [
        {"iss": "https://untrusted.example/"},
        {"aud": "other"},
        {"exp": 1},
        {"sub": "not-a-uuid"},
        {"iat": int(time.time()) + 3600},
    ],
)
def test_invalid_signed_identity_cannot_access_review_store(setup, change):
    _, client, key, _ = setup
    response = client.get("/v1/policy-reviews/drafts/" + DIGEST, headers=token(key, **change))
    assert response.status_code == 401


def test_wrong_signature_and_untrusted_roles_do_not_grant_access(setup):
    _, client, key, _ = setup
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = "/v1/policy-reviews/drafts/" + DIGEST
    assert client.get(path, headers=token(other_key)).status_code == 401
    assert (
        client.get(path, headers=token(key, sub=str(uuid.uuid4()), roles=["admin"])).status_code
        == 403
    )


@pytest.mark.parametrize("allowed", [[], ["invalid-subject"]])
def test_missing_or_invalid_operator_configuration_fails_closed(setup, allowed):
    _, client, key, settings = setup
    settings.policy_reviewer_subjects = allowed
    response = client.get("/v1/policy-reviews/drafts/" + DIGEST, headers=token(key))
    assert response.status_code == 503


def allow_database(app):
    async def db():
        yield object()

    app.dependency_overrides[api.review_db] = db


def test_valid_identity_reaches_protected_read_only(setup, monkeypatch):
    app, client, key, _ = setup
    allow_database(app)
    reader = AsyncMock(return_value={"draft_digest": DIGEST, "production_approved": False})
    monkeypatch.setattr(api.store, "read_draft", reader)
    response = client.get("/v1/policy-reviews/drafts/" + DIGEST, headers=token(key))
    assert response.status_code == 200 and not response.json()["production_approved"]
    reader.assert_awaited_once()


@pytest.mark.parametrize(
    "extra",
    [{"reviewer_id": str(SUBJECT)}, {"approved": True}, {"created_at": "2026-01-01T00:00:00Z"}],
)
def test_client_cannot_choose_reviewer_timestamp_or_approval(setup, extra):
    app, client, key, _ = setup
    allow_database(app)
    response = client.post(
        "/v1/policy-reviews/drafts/" + DIGEST + "/reviews",
        headers=token(key),
        json={
            "request_key": str(uuid.uuid4()),
            "expected_revision": 0,
            "action": "reject",
            "reason": "Synthetic",
            **extra,
        },
    )
    assert response.status_code == 422


def test_decision_actor_is_taken_from_verified_token(setup, monkeypatch):
    app, client, key, _ = setup
    allow_database(app)
    reviewer = AsyncMock(return_value={"production_approved": False})
    monkeypatch.setattr(api.store, "review_draft", reviewer)
    response = client.post(
        "/v1/policy-reviews/drafts/" + DIGEST + "/reviews",
        headers=token(key),
        json={
            "request_key": str(uuid.uuid4()),
            "expected_revision": 0,
            "action": "reject",
            "reason": "Synthetic",
        },
    )
    assert response.status_code == 200
    actor = reviewer.call_args.args[1]
    assert actor.subject == SUBJECT and actor.issuer == ISSUER


@pytest.mark.parametrize(
    "body",
    [
        '{"request_key":"x","request_key":"y"}',
        '{"request_key":"00000000-0000-4000-8000-000000000123",'
        '"draft_json":"{}","sources_base64":{"wording":"@@@@"}}',
    ],
)
def test_ambiguous_json_and_invalid_pdf_encoding_fail_sanitized(setup, body):
    app, client, key, _ = setup
    allow_database(app)
    response = client.post("/v1/policy-reviews/drafts", headers=token(key), content=body)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid policy-review draft or source evidence."}


@pytest.mark.parametrize("endpoint", ["reviews", "import-checks"])
def test_decision_commands_reject_ambiguous_json_and_oversized_bodies(setup, endpoint):
    app, client, key, _ = setup
    allow_database(app)
    path = "/v1/policy-reviews/drafts/" + DIGEST + "/" + endpoint
    response = client.post(
        path, headers=token(key), content='{"request_key":"a","request_key":"b"}'
    )
    assert response.status_code == 422
    assert client.post(path, headers=token(key), content=" " * 17000).status_code == 413
