"""Authenticated identity must gate consent and profile-memory access."""

from __future__ import annotations

import time
import uuid
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app.api.v1 import consent as consent_api
from app.api.v1 import message as message_api
from app.core import security
from app.core.config import Settings
from app.main import app
from app.models.db.user_profile_memory import UserProfileMemory

USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000123")
OTHER_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000456")
ISSUER = "https://identity.example.test/"
AUDIENCE = "insuranceai-api"
JWKS_URL = "https://identity.example.test/.well-known/jwks.json"


@pytest.mark.parametrize("environment", ["development", "staging", "production", "test", "qa"])
@pytest.mark.parametrize("token", [None, "test-token", "development"])
def test_no_environment_or_default_token_can_bypass_profile_auth(
    environment: str, token: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail if a default/dev identity ever enables protected storage in any mode."""
    for key in ("AUTH_ISSUER", "AUTH_AUDIENCE", "AUTH_JWKS_URL"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=None, environment=environment)
    assert (settings.auth_issuer, settings.auth_audience, settings.auth_jwks_url) == ("", "", "")
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    monkeypatch.setattr(consent_api, "AsyncSessionLocal", _forbidden_db)
    monkeypatch.setattr(message_api, "AsyncSessionLocal", _forbidden_db)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    # No lifespan needed for identity tests: the actual dependency and routes run.
    client = TestClient(app)
    responses = [
        client.post("/v1/consent", headers=headers, json={
            "user_id": str(USER_ID), "scope": "save_profile", "action": "grant",
        }),
        client.delete(f"/v1/profile-memory/{USER_ID}", headers=headers),
        client.post("/v1/message", headers=headers, json={
            "user_id": str(USER_ID), "user_message": "Use saved profile",
        }),
    ]
    assert [response.status_code for response in responses] == [
        503, 503, 503 if token else 401,
    ]


@pytest.fixture
def trusted_identity(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Use a real RSA signature while replacing only the remote JWKS fetch."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    settings = SimpleNamespace(
        auth_issuer=ISSUER,
        auth_audience=AUDIENCE,
        auth_jwks_url=JWKS_URL,
    )
    def _get_signing_key(token: str) -> Any:
        return SimpleNamespace(key=public_key)

    jwks_client = SimpleNamespace(get_signing_key_from_jwt=_get_signing_key)

    def _get_jwks(url: str) -> Any:
        return jwks_client

    monkeypatch.setattr(security, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "_jwks_client", _get_jwks)
    return private_key


def _claims() -> dict[str, Any]:
    now = int(time.time())
    return {
        "sub": str(USER_ID),
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + 300,
    }


def _token(private_key: Any, claims: dict[str, Any] | None = None) -> str:
    return jwt.encode(claims or _claims(), private_key, algorithm="RS256", headers={"kid": "test"})


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _noop_trace(*args: Any, **kwargs: Any) -> nullcontext[None]:
    return nullcontext(None)


def _forbidden_db() -> None:
    raise AssertionError("Unauthenticated request reached profile storage")


def test_valid_signed_token_binds_identity(trusted_identity: Any) -> None:
    assert security.require_authenticated_user_id(_bearer(_token(trusted_identity))) == USER_ID


@pytest.mark.parametrize(
    "change",
    [
        {"iss": "https://untrusted.example.test/"},
        {"aud": "another-api"},
        {"exp": 1},
        {"iat": int(time.time()) + 3600},
        {"sub": "not-a-uuid"},
    ],
)
def test_invalid_token_claims_fail_closed(trusted_identity: Any, change: dict[str, Any]) -> None:
    claims = _claims()
    claims.update(change)
    with pytest.raises(HTTPException) as error:
        security.require_authenticated_user_id(_bearer(_token(trusted_identity, claims)))
    assert error.value.status_code == 401


def test_invalid_signature_fails_closed(trusted_identity: Any) -> None:
    other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(HTTPException) as error:
        security.require_authenticated_user_id(_bearer(_token(other_private_key)))
    assert error.value.status_code == 401


def test_missing_token_and_identity_configuration_fail_closed(
    trusted_identity: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(HTTPException) as error:
        security.require_authenticated_user_id(None)
    assert error.value.status_code == 401

    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(auth_issuer="", auth_audience="", auth_jwks_url=""),
    )
    with pytest.raises(HTTPException) as error:
        security.require_authenticated_user_id(None)
    assert error.value.status_code == 503


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "POST",
            "/v1/consent",
            {"user_id": str(USER_ID), "scope": "save_profile", "action": "grant"},
        ),
        ("DELETE", f"/v1/profile-memory/{USER_ID}", None),
        (
            "POST",
            "/v1/message",
            {"user_id": str(USER_ID), "user_message": "My profile"},
        ),
    ],
)
def test_profile_routes_reject_missing_token_before_storage(
    trusted_identity: Any,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    payload: dict[str, str] | None,
) -> None:
    monkeypatch.setattr(consent_api, "AsyncSessionLocal", _forbidden_db)
    monkeypatch.setattr(message_api, "AsyncSessionLocal", _forbidden_db)
    with TestClient(app) as client:
        response = client.request(method, path, json=payload)
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "POST",
            "/v1/consent",
            {"user_id": str(OTHER_USER_ID), "scope": "save_profile", "action": "grant"},
        ),
        ("DELETE", f"/v1/profile-memory/{OTHER_USER_ID}", None),
        (
            "POST",
            "/v1/message",
            {"user_id": str(OTHER_USER_ID), "user_message": "Another profile"},
        ),
    ],
)
def test_profile_routes_reject_subject_mismatch_before_storage(
    trusted_identity: Any,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    payload: dict[str, str] | None,
) -> None:
    monkeypatch.setattr(consent_api, "AsyncSessionLocal", _forbidden_db)
    monkeypatch.setattr(message_api, "AsyncSessionLocal", _forbidden_db)
    with TestClient(app) as client:
        response = client.request(
            method,
            path,
            json=payload,
            headers={"Authorization": f"Bearer {_token(trusted_identity)}"},
        )
    assert response.status_code == 403


def test_unconfigured_identity_rejects_profile_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(auth_issuer="", auth_audience="", auth_jwks_url=""),
    )
    monkeypatch.setattr(consent_api, "AsyncSessionLocal", _forbidden_db)
    with TestClient(app) as client:
        response = client.post(
            "/v1/consent",
            json={"user_id": str(USER_ID), "scope": "save_profile", "action": "grant"},
        )
    assert response.status_code == 503


def test_authenticated_consent_and_deletion_use_token_subject(
    trusted_identity: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = AsyncMock()
    db.__aenter__.return_value = db
    db.execute.return_value = MagicMock(rowcount=1)
    monkeypatch.setattr(consent_api, "AsyncSessionLocal", lambda: db)
    headers = {"Authorization": f"Bearer {_token(trusted_identity)}"}
    with TestClient(app) as client:
        consent_response = client.post(
            "/v1/consent",
            json={"user_id": str(USER_ID), "scope": "save_profile", "action": "grant"},
            headers=headers,
        )
        deletion_response = client.delete(f"/v1/profile-memory/{USER_ID}", headers=headers)
    assert consent_response.status_code == 200
    assert consent_response.json()["user_id"] == str(USER_ID)
    assert deletion_response.status_code == 200
    assert deletion_response.json() == {"user_id": str(USER_ID), "deleted": True}
    assert db.commit.await_count == 2


def test_anonymous_message_stays_available_without_profile_storage(
    trusted_identity: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = SimpleNamespace(
        aget_state=AsyncMock(return_value=None),
        ainvoke=AsyncMock(return_value={"delivery_hold": True, "missing_fields": ["age"]}),
    )
    monkeypatch.setattr(message_api, "_app_graph", graph)
    monkeypatch.setattr(message_api, "AsyncSessionLocal", _forbidden_db)
    monkeypatch.setattr(message_api, "request_trace", _noop_trace)
    with TestClient(app) as client:
        response = client.post("/v1/message", json={"user_message": "Help with health cover"})
    assert response.status_code == 200
    assert response.json()["delivery_hold"] is True
    state = graph.ainvoke.await_args.args[0]
    assert state["user_id"] is None
    assert state["consent"] == {"granted": False, "scopes": []}


# ── Cross-user isolation (user requested explicitly) ─────────────────────────


def test_user_a_cannot_grant_consent_for_user_b(
    trusted_identity: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid token for USER_ID must not grant consent for OTHER_USER_ID."""
    monkeypatch.setattr(consent_api, "AsyncSessionLocal", _forbidden_db)
    with TestClient(app) as client:
        response = client.post(
            "/v1/consent",
            json={"user_id": str(OTHER_USER_ID), "scope": "save_profile", "action": "grant"},
            headers={"Authorization": f"Bearer {_token(trusted_identity)}"},
        )
    assert response.status_code == 403


def test_user_a_cannot_revoke_consent_for_user_b(
    trusted_identity: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid token for USER_ID must not revoke consent for OTHER_USER_ID."""
    monkeypatch.setattr(consent_api, "AsyncSessionLocal", _forbidden_db)
    with TestClient(app) as client:
        response = client.post(
            "/v1/consent",
            json={"user_id": str(OTHER_USER_ID), "scope": "save_profile", "action": "revoke"},
            headers={"Authorization": f"Bearer {_token(trusted_identity)}"},
        )
    assert response.status_code == 403


def test_user_a_cannot_delete_user_b_profile(
    trusted_identity: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid token for USER_ID must not delete OTHER_USER_ID's profile memory."""
    monkeypatch.setattr(consent_api, "AsyncSessionLocal", _forbidden_db)
    with TestClient(app) as client:
        response = client.delete(
            f"/v1/profile-memory/{OTHER_USER_ID}",
            headers={"Authorization": f"Bearer {_token(trusted_identity)}"},
        )
    assert response.status_code == 403


def test_user_a_cannot_send_message_as_user_b(
    trusted_identity: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid token for USER_ID must not load or write profile data for OTHER_USER_ID."""
    monkeypatch.setattr(message_api, "AsyncSessionLocal", _forbidden_db)
    with TestClient(app) as client:
        response = client.post(
            "/v1/message",
            json={"user_id": str(OTHER_USER_ID), "user_message": "Load another profile"},
            headers={"Authorization": f"Bearer {_token(trusted_identity)}"},
        )
    assert response.status_code == 403


def test_consent_revoke_requires_same_verified_token(
    trusted_identity: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Consent revoke requires a verified token matching the user_id, not just any token."""
    monkeypatch.setattr(consent_api, "AsyncSessionLocal", _forbidden_db)
    with TestClient(app) as client:
        # No token: rejected
        no_token = client.post(
            "/v1/consent",
            json={"user_id": str(USER_ID), "scope": "save_profile", "action": "revoke"},
        )
        assert no_token.status_code == 401

        # Token for a different user (signed by trusted key, but sub != user_id): 403
        other_claims = _claims()
        other_claims["sub"] = str(OTHER_USER_ID)
        wrong_subject = client.post(
            "/v1/consent",
            json={"user_id": str(USER_ID), "scope": "save_profile", "action": "revoke"},
            headers={"Authorization": f"Bearer {_token(trusted_identity, other_claims)}"},
        )
        assert wrong_subject.status_code == 403


def test_deletion_requires_same_verified_token(
    trusted_identity: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Profile deletion requires a verified token matching the user_id."""
    monkeypatch.setattr(consent_api, "AsyncSessionLocal", _forbidden_db)
    with TestClient(app) as client:
        # No token: rejected
        no_token = client.delete(f"/v1/profile-memory/{USER_ID}")
        assert no_token.status_code == 401

        # Token for a different user (signed by trusted key, but sub != user_id): 403
        other_claims = _claims()
        other_claims["sub"] = str(OTHER_USER_ID)
        wrong_subject = client.delete(
            f"/v1/profile-memory/{USER_ID}",
            headers={"Authorization": f"Bearer {_token(trusted_identity, other_claims)}"},
        )
        assert wrong_subject.status_code == 403


def test_authenticated_message_loads_only_the_verified_subject_profile(
    trusted_identity: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = AsyncMock()
    db.__aenter__.return_value = db
    db_result = MagicMock()
    db_result.scalars.return_value.all.return_value = ["save_profile"]
    db.execute.return_value = db_result
    db.get.return_value = SimpleNamespace(profile_snapshot_json={"age": 35})
    graph = SimpleNamespace(
        aget_state=AsyncMock(return_value=None),
        ainvoke=AsyncMock(return_value={"delivery_hold": True, "missing_fields": ["age"]}),
    )
    monkeypatch.setattr(message_api, "AsyncSessionLocal", lambda: db)
    monkeypatch.setattr(message_api, "_app_graph", graph)
    monkeypatch.setattr(message_api, "request_trace", _noop_trace)
    with TestClient(app) as client:
        response = client.post(
            "/v1/message",
            json={"user_message": "Use my saved details"},
            headers={"Authorization": f"Bearer {_token(trusted_identity)}"},
        )
    assert response.status_code == 200
    db.get.assert_awaited_once_with(UserProfileMemory, USER_ID)
    state = graph.ainvoke.await_args.args[0]
    assert state["user_id"] == str(USER_ID)
    assert state["user_profile"] == {"age": 35}
    assert state["consent"] == {"granted": True, "scopes": ["save_profile"]}


# ── Session ownership tests ──────────────────────────────────────────────────


def test_user_a_cannot_continue_user_b_session(
    trusted_identity: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User A (USER_ID) cannot continue a session owned by User B (OTHER_USER_ID)."""
    from app.models.db.session import Session as DBSession

    db = AsyncMock()
    db.__aenter__.return_value = db
    db_result = MagicMock()
    empty_scopes: list[str] = []
    db_result.scalars.return_value.all.return_value = empty_scopes
    db.execute.return_value = db_result
    # Session exists in DB and belongs to OTHER_USER_ID
    db.get.return_value = DBSession(
        id=uuid.uuid4(), user_id=OTHER_USER_ID, intent="health"
    )
    checkpoint = SimpleNamespace(
        values={"messages": [{"role": "user", "content": "hi"}], "user_id": str(OTHER_USER_ID)}
    )
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=checkpoint))

    monkeypatch.setattr(message_api, "AsyncSessionLocal", lambda: db)
    monkeypatch.setattr(message_api, "_app_graph", graph)
    monkeypatch.setattr(message_api, "request_trace", _noop_trace)

    with TestClient(app) as client:
        response = client.post(
            "/v1/message",
            json={"session_id": "session-owned-by-b", "user_message": "Continuing as user A"},
            headers={"Authorization": f"Bearer {_token(trusted_identity)}"},
        )
    assert response.status_code == 403


def test_user_a_cannot_read_user_b_session(
    trusted_identity: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User A (USER_ID) cannot read session details of User B (OTHER_USER_ID)."""
    from app.api.v1 import sessions as sessions_api
    from app.models.db.session import Session as DBSession

    db = AsyncMock()
    db.__aenter__.return_value = db
    db.get.return_value = DBSession(
        id=uuid.uuid4(), user_id=OTHER_USER_ID, intent="health"
    )
    checkpoint = SimpleNamespace(
        values={"messages": [{"role": "user", "content": "hi"}], "user_id": str(OTHER_USER_ID)}
    )
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=checkpoint))

    monkeypatch.setattr(sessions_api, "AsyncSessionLocal", lambda: db)
    monkeypatch.setattr(message_api, "_app_graph", graph)

    with TestClient(app) as client:
        response = client.get(
            "/v1/session/session-owned-by-b",
            headers={"Authorization": f"Bearer {_token(trusted_identity)}"},
        )
    assert response.status_code == 403


def test_authenticated_session_cannot_be_continued_anonymously(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An authenticated session cannot be continued without a verified token."""
    from app.models.db.session import Session as DBSession

    db = AsyncMock()
    db.__aenter__.return_value = db
    db.get.return_value = DBSession(
        id=uuid.uuid4(), user_id=OTHER_USER_ID, intent="health"
    )
    checkpoint = SimpleNamespace(
        values={"messages": [{"role": "user", "content": "hi"}], "user_id": str(OTHER_USER_ID)}
    )
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=checkpoint))

    monkeypatch.setattr(message_api, "AsyncSessionLocal", lambda: db)
    monkeypatch.setattr(message_api, "_app_graph", graph)
    monkeypatch.setattr(message_api, "request_trace", _noop_trace)

    with TestClient(app) as client:
        response = client.post(
            "/v1/message",
            json={"session_id": "session-owned-by-b", "user_message": "Anonymous attempt"},
        )
    assert response.status_code == 401


def test_authenticated_session_cannot_be_read_anonymously(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An authenticated session cannot be read without a verified token."""
    from app.api.v1 import sessions as sessions_api
    from app.models.db.session import Session as DBSession

    db = AsyncMock()
    db.__aenter__.return_value = db
    db.get.return_value = DBSession(
        id=uuid.uuid4(), user_id=OTHER_USER_ID, intent="health"
    )
    checkpoint = SimpleNamespace(
        values={"messages": [{"role": "user", "content": "hi"}], "user_id": str(OTHER_USER_ID)}
    )
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=checkpoint))

    monkeypatch.setattr(sessions_api, "AsyncSessionLocal", lambda: db)
    monkeypatch.setattr(message_api, "_app_graph", graph)

    with TestClient(app) as client:
        response = client.get("/v1/session/session-owned-by-b")
    assert response.status_code == 401


def test_owner_can_read_own_session(
    trusted_identity: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Session owner can read their own session details."""
    from app.api.v1 import sessions as sessions_api
    from app.models.db.session import Session as DBSession

    db = AsyncMock()
    db.__aenter__.return_value = db
    db.get.return_value = DBSession(
        id=uuid.uuid4(), user_id=USER_ID, intent="health"
    )
    checkpoint = SimpleNamespace(
        values={
            "messages": [{"role": "user", "content": "hello"}],
            "user_id": str(USER_ID),
            "intent": "health",
            "approved": True,
            "delivery_hold": False,
            "escalation": False,
            "advisor_notification": {},
            "output": {
                "report_status": "ready",
                "reply": "Verified synthetic response",
                "sentences": [{"text": "Verified synthetic response"}],
            },
            "retrieved_facts": [],
            "calculator_outputs": {},
        }
    )
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=checkpoint))

    monkeypatch.setattr(sessions_api, "AsyncSessionLocal", lambda: db)
    monkeypatch.setattr(message_api, "_app_graph", graph)

    with TestClient(app) as client:
        response = client.get(
            "/v1/session/my-own-session",
            headers={"Authorization": f"Bearer {_token(trusted_identity)}"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "my-own-session"
    assert data["intent"] == "health"
    assert len(data["messages"]) == 1


def test_nonexistent_session_returns_404(
    trusted_identity: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Querying a non-existent session returns 404."""
    from app.api.v1 import sessions as sessions_api

    db = AsyncMock()
    db.__aenter__.return_value = db
    db.get.return_value = None
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=None))

    monkeypatch.setattr(sessions_api, "AsyncSessionLocal", lambda: db)
    monkeypatch.setattr(message_api, "_app_graph", graph)

    with TestClient(app) as client:
        response = client.get(
            "/v1/session/no-such-session",
            headers={"Authorization": f"Bearer {_token(trusted_identity)}"},
        )
    assert response.status_code == 404
