"""Closed activity API and bounded, non-transcript response projection."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.v1 import voice_activity as api
from app.core import security
from app.core.config import Settings
from app.voice.activity import ActivityRecapService


def configured(owner):
    return Settings(
        _env_file=None,
        auth_provider="clerk",
        environment="staging",
        auth_issuer="https://synthetic.clerk.test",
        voice_tools_enabled=True,
        voice_case_binding_enabled=True,
        voice_test_subjects=[str(owner)],
    )


def service_and_db(rows):
    owner, session = uuid.uuid4(), uuid.uuid4()
    db = AsyncMock()
    db.scalar.return_value = True
    db.scalars.return_value = Mock(all=Mock(return_value=rows))
    context = AsyncMock()
    context.__aenter__.return_value = db
    service = ActivityRecapService(lambda: context, configured(owner))
    service.locked = AsyncMock(
        return_value=(None, SimpleNamespace(state="active"), SimpleNamespace(synthetic=True), None)
    )
    service.authorize_summary = AsyncMock()
    service.now = AsyncMock(return_value=datetime.now(UTC))
    return owner, session, service, db


def row(state="pending", **changes):
    values = dict(
        response_id=1,
        state=state,
        intent="report",
        answer_kind=None,
        created_at=datetime.now(UTC),
        completed_at=None,
    )
    values.update(changes)
    return SimpleNamespace(**values)


def test_activity_api_auth_owner_scope_no_store_and_invalid_identifier(monkeypatch):
    app = FastAPI()
    app.include_router(api.router)
    client = TestClient(app)
    owner, session = uuid.uuid4(), uuid.uuid4()
    settings = Settings(
        _env_file=None,
        auth_provider="legacy_oidc",
        auth_issuer="https://synthetic.test",
        auth_audience="synthetic",
        auth_jwks_url="https://synthetic.test/jwks",
    )
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    endpoint = f"/voice/development/sessions/{session}/activity-recap"
    assert client.get(endpoint).status_code == 401
    app.dependency_overrides[security.require_authenticated_user_id] = lambda: owner
    reader = AsyncMock(return_value={"kind": "voice_session_activity_recap"})
    monkeypatch.setattr(
        api, "ActivityRecapService", lambda *args: SimpleNamespace(read_activity=reader)
    )
    response = client.get(endpoint)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    reader.assert_awaited_once_with(owner, session)
    assert client.get("/voice/development/sessions/not-a-uuid/activity-recap").status_code == 422
    assert (
        client.post(endpoint, json={"owner_id": str(uuid.uuid4()), "approved": True}).status_code
        == 405
    )


@pytest.mark.asyncio
async def test_missing_storage_fails_closed_before_owner_or_authority_read():
    owner, session, service, db = service_and_db([])
    db.scalar.return_value = False
    with pytest.raises(HTTPException) as error:
        await service.read_activity(owner, session)
    assert error.value.status_code == 503
    service.locked.assert_not_awaited()
    service.authorize_summary.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state,status",
    [
        ("pending", "pending"),
        ("prepared", "pending"),
        ("send_unknown", "delivery_uncertain"),
        ("interrupted", "interrupted"),
        ("failed", "failed"),
        ("sent", "response_sent"),
    ],
)
async def test_activity_never_promotes_socket_receipts_to_audible_delivery(state, status):
    receipt = row(state, intent="unsupported", answer_kind="operational")
    owner, session, service, db = service_and_db([receipt])
    value = await service.read_activity(owner, session)
    assert value["events"][0]["status"] == status
    assert value["reviewed_report"] is None and value["report_availability"] == "not_sent"
    assert value["transcript_stored"] is False and value["audio_delivery_verified"] is False
    assert set(value["events"][0]) == {
        "response_id",
        "intent",
        "status",
        "answer_kind",
        "created_at",
        "completed_at",
    }
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"state": "audio_delivered"},
        {"intent": "approved_by_provider"},
        {"answer_kind": "raw_transcript"},
    ],
)
async def test_corrupt_receipt_vocabularies_are_not_projected(changes):
    owner, session, service, db = service_and_db([row(**changes)])
    with pytest.raises(HTTPException) as error:
        await service.read_activity(owner, session)
    assert error.value.status_code == 409
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_activity_event_budget_fails_closed_instead_of_silently_truncating():
    owner, session, service, db = service_and_db([row(response_id=i) for i in range(129)])
    with pytest.raises(HTTPException) as error:
        await service.read_activity(owner, session)
    assert error.value.status_code == 409
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_activity_authorization_is_not_returned():
    owner, session, service, db = service_and_db([])
    now = datetime.now(UTC)
    service.now.side_effect = [now, now + timedelta(seconds=11)]
    with pytest.raises(HTTPException) as error:
        await service.read_activity(owner, session)
    assert error.value.status_code == 409
    db.commit.assert_not_awaited()


def test_activity_requires_explicit_development_binding_gate():
    owner = uuid.uuid4()
    settings = Settings(_env_file=None)
    with pytest.raises(HTTPException) as error:
        ActivityRecapService(None, settings).binding_gate(owner)
    assert error.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("recap_storage", [False, True])
async def test_summary_revoke_erases_optional_ciphertext_when_table_exists(
    monkeypatch, recap_storage
):
    from app.api.v1 import consent as consent_api
    from app.voice.service import VoiceSessionService

    owner = uuid.uuid4()
    settings = Settings(_env_file=None, auth_provider="clerk")
    db = AsyncMock()
    db.scalar.return_value = recap_storage
    db.add = Mock()
    context = AsyncMock()
    context.__aenter__.return_value = db
    monkeypatch.setattr(consent_api, "AsyncSessionLocal", lambda: context)
    monkeypatch.setattr(consent_api, "get_settings", lambda: settings)
    monkeypatch.setattr(VoiceSessionService, "lock_entitlement", AsyncMock(return_value=None))
    result = await consent_api.update_consent(
        consent_api.ConsentRequest(user_id=owner, scope="voice_summary", action="revoke"), owner
    )
    assert result.status == "revoked"
    statements = [str(call.args[0]) for call in db.execute.await_args_list]
    erased = [sql for sql in statements if sql.startswith("UPDATE voice_recaps")]
    assert len(erased) == int(recap_storage)
    if erased:
        assert "encrypted_content" in erased[0] and "user_id" in erased[0]
    db.commit.assert_awaited_once()
