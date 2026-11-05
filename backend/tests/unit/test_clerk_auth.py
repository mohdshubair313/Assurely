"""Real RSA verification with synthetic keys; no Clerk account is simulated as live."""

import time
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app.api.v1.identity import router
from app.core import security
from app.core.config import Settings
from app.db import auth_identity

LOCAL = uuid.UUID("00000000-0000-4000-8000-000000000123")
ISSUER = "https://synthetic.clerk.accounts.dev"
ORIGIN = "http://localhost:3000"


@pytest.fixture
def setup(monkeypatch):
    settings = Settings(
        _env_file=None,
        auth_provider="clerk",
        auth_issuer=ISSUER,
        auth_jwks_url=ISSUER + "/.well-known/jwks.json",
        auth_authorized_parties=[ORIGIN],
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    jwks = SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key()))
    monkeypatch.setattr(security, "_jwks_client", lambda _: jwks)
    resolve = Mock(return_value=LOCAL)
    monkeypatch.setattr(auth_identity, "resolve_identity", resolve)
    return settings, key, resolve


def claims(**change):
    now = int(time.time())
    return {
        "sub": "user_synthetic123",
        "sid": "sess_synthetic123",
        "v": 2,
        "iss": ISSUER,
        "azp": ORIGIN,
        "iat": now,
        "nbf": now - 1,
        "exp": now + 60,
        **change,
    }


def bearer(key, payload=None):
    return HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=jwt.encode(
            claims() if payload is None else payload,
            key,
            algorithm="RS256",
            headers={"kid": "fixture"},
        ),
    )


def test_clerk_without_audience_maps_verified_immutable_subject(setup):
    _, key, resolve = setup
    assert security.require_authenticated_user_id(bearer(key)) == LOCAL
    resolve.assert_called_once_with(ISSUER, "user_synthetic123")


@pytest.mark.parametrize(
    "change",
    [
        {"iss": "https://other.example"},
        {"azp": "https://attacker.example"},
        {"azp": ORIGIN + "/"},
        {"azp": None},
        {"sts": "pending"},
        {"exp": 1},
        {"nbf": int(time.time()) + 3600},
        {"iat": int(time.time()) + 3600},
        {"sub": str(LOCAL)},
        {"sub": "m2m_other"},
        {"sid": "oauth_other"},
        {"sid": None},
        {"v": 1},
        {"v": True},
        {"sub": {"id": "user_bad"}},
        {"azp": [ORIGIN]},
        {"o": "invalid-organization-object"},
        {"o": ["invalid-organization-object"]},
    ],
)
def test_untrusted_claims_rejected_before_identity_storage(setup, change):
    _, key, resolve = setup
    with pytest.raises(HTTPException) as exc:
        security.require_authenticated_user_id(bearer(key, claims(**change)))
    assert exc.value.status_code == 401
    resolve.assert_not_called()


@pytest.mark.parametrize("field", ["sub", "sid", "v", "azp", "exp", "nbf", "iat", "iss"])
def test_required_session_claims(setup, field):
    _, key, resolve = setup
    payload = claims()
    payload.pop(field)
    with pytest.raises(HTTPException) as exc:
        security.require_authenticated_user_id(bearer(key, payload))
    assert exc.value.status_code == 401
    resolve.assert_not_called()


def test_invalid_signature_and_symmetric_substitution(setup):
    _, key, resolve = setup
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(
        claims(),
        "synthetic-only-key-with-32-characters",
        algorithm="HS256",
        headers={"kid": "fixture"},
    )
    for credential in (
        bearer(other),
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=forged),
    ):
        with pytest.raises(HTTPException) as exc:
            security.require_authenticated_user_id(credential)
        assert exc.value.status_code == 401
    resolve.assert_not_called()


def test_optional_audience_is_validated_when_configured(setup):
    settings, key, _ = setup
    settings.auth_audience = "assurely-api"
    for payload in (claims(), claims(aud="another-api")):
        with pytest.raises(HTTPException) as exc:
            security.require_authenticated_user_id(bearer(key, payload))
        assert exc.value.status_code == 401
    assert security.require_authenticated_user_id(bearer(key, claims(aud="assurely-api"))) == LOCAL


@pytest.mark.parametrize(
    "field,value",
    [
        ("auth_authorized_parties", []),
        ("auth_authorized_parties", ["*"]),
        ("auth_jwks_url", "https://another.example/.well-known/jwks.json"),
        ("auth_provider", "automatic"),
    ],
)
def test_configuration_fails_closed(setup, field, value):
    settings, key, resolve = setup
    setattr(settings, field, value)
    with pytest.raises(HTTPException) as exc:
        security.require_authenticated_user_id(bearer(key))
    assert exc.value.status_code == 503
    resolve.assert_not_called()


def test_production_cannot_use_clerk_development_instance(setup):
    settings, key, _ = setup
    settings.environment = "production"
    settings.auth_authorized_parties = ["https://assurely.example"]
    with pytest.raises(HTTPException) as exc:
        security.require_authenticated_user_id(bearer(key))
    assert exc.value.status_code == 503


def test_jwks_outage_is_unavailable_not_an_invalid_login(setup, monkeypatch):
    _, key, resolve = setup

    def unavailable(_):
        raise jwt.PyJWKClientConnectionError("synthetic outage")

    monkeypatch.setattr(security, "_jwks_client", unavailable)
    with pytest.raises(HTTPException) as exc:
        security.require_authenticated_user_id(bearer(key))
    assert exc.value.status_code == 503
    resolve.assert_not_called()


def test_me_and_admin_are_resource_protected_and_ignore_token_roles(setup):
    settings, key, _ = setup
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    client = TestClient(app)
    assert client.get("/v1/me").status_code == 401
    signed = bearer(key, claims(role="admin", public_metadata={"role": "admin"})).credentials
    headers = {"Authorization": "Bearer " + signed}
    assert client.get("/v1/me", headers=headers).json() == {
        "user_id": str(LOCAL),
        "roles": ["customer"],
        "provider": "clerk",
    }
    settings.policy_reviewer_subjects = [str(LOCAL)]
    assert security.server_roles(LOCAL) == {"customer", "qualified_policy_reviewer"}
    assert (
        client.post(
            f"/v1/admin/escalations/{uuid.uuid4()}/assign",
            headers=headers,
            json={"advisor_id": str(LOCAL), "reason": "test"},
        ).status_code
        == 403
    )
    settings.admin_subjects = [str(LOCAL)]
    assert "admin" in security.server_roles(LOCAL)
    settings.auth_test_subjects = [str(LOCAL)]
    assert security.server_roles(LOCAL) == {"customer"}


def test_anonymous_messages_are_disallowed_in_clerk_mode(setup):
    with pytest.raises(HTTPException) as exc:
        security.optional_authenticated_user_id(None)
    assert exc.value.status_code == 401


def test_account_switch_cannot_retarget_owned_records(setup):
    with pytest.raises(HTTPException) as exc:
        security.require_matching_user_id(LOCAL, uuid.uuid4())
    assert exc.value.status_code == 403


def test_new_session_token_refresh_preserves_identity_and_expired_token_is_rejected(setup):
    _, key, resolve = setup
    assert security.require_authenticated_user_id(bearer(key)) == LOCAL
    now = int(time.time())
    expired = claims(iat=now - 120, nbf=now - 120, exp=now - 60)
    with pytest.raises(HTTPException):
        security.require_authenticated_user_id(bearer(key, expired))
    assert security.require_authenticated_user_id(bearer(key, claims(exp=now + 120))) == LOCAL
    assert resolve.call_count == 2


def test_jwks_unknown_key_rotation_fetches_fresh_keys(setup, monkeypatch):
    _, key, _ = setup
    rotating = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    advertised = [key]
    calls = []

    def fetch(client):
        calls.append(1)
        data = {
            "keys": [
                {
                    **jwt.algorithms.RSAAlgorithm.to_jwk(item.public_key(), as_dict=True),
                    "kid": "old" if item is key else "new",
                    "use": "sig",
                }
                for item in advertised
            ]
        }
        client.jwk_set_cache.put(data)
        return data

    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", fetch)
    client = jwt.PyJWKClient(ISSUER + "/.well-known/jwks.json", cache_jwk_set=True)
    monkeypatch.setattr(security, "_jwks_client", lambda _: client)

    def credential(item, kid):
        return HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=jwt.encode(claims(), item, algorithm="RS256", headers={"kid": kid}),
        )

    assert security.require_authenticated_user_id(credential(key, "old")) == LOCAL
    assert security.require_authenticated_user_id(credential(key, "old")) == LOCAL
    assert len(calls) == 1
    advertised[:] = [rotating]
    assert security.require_authenticated_user_id(credential(rotating, "new")) == LOCAL
    assert len(calls) == 2


def test_designated_test_accounts_cannot_exercise_review_or_advisor_roles(setup, monkeypatch):
    from app.core import advisor_auth, policy_review_auth

    settings, _, _ = setup
    settings.auth_test_subjects = [str(LOCAL)]
    settings.advisor_subjects = [str(LOCAL)]
    settings.policy_reviewer_subjects = [str(LOCAL)]
    settings.policy_publisher_subjects = [str(LOCAL)]
    for module in (advisor_auth, policy_review_auth):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    for guard in (
        advisor_auth.require_advisor,
        policy_review_auth.require_policy_reviewer,
        policy_review_auth.require_policy_publisher,
    ):
        with pytest.raises(HTTPException) as exc:
            guard(LOCAL)
        assert exc.value.status_code == 403
