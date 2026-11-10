"""Synthetic caption projection, closed commands and authenticated API boundaries."""

import copy
import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.v1 import voice_development as api
from app.core import security
from app.core.config import Settings
from app.db.schema import compatible_schema
from app.voice.case_binding import BindCaseCommand, VoiceCaseBindingService, reviewed_caption_packet


@pytest.fixture
def output():
    reference = {
        "source_id": "synthetic-policy",
        "pdf_page": 3,
        "clause": "Synthetic scope",
        "quote": "Only the stated synthetic scope applies.",
        "url": "https://example.test/policy.pdf",
        "sha256": "a" * 64,
    }
    citation = {
        "id": "R1",
        "source": "Synthetic reviewed fixture",
        "url": reference["url"],
        "last_verified": datetime.now(UTC).date().isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "references": [reference],
        "applicability_evidence": [reference],
        "condition_evidence": [reference],
    }
    return {
        "report_status": "reviewed_report_held",
        "sentences": [
            {
                "text": "The stated scope applies only when its conditions hold.",
                "citations": [citation],
            }
        ],
    }


def test_caption_projection_preserves_whole_sentences_conditions_and_source_dates(output):
    before = copy.deepcopy(output)
    packet = reviewed_caption_packet(output)
    assert output == before
    assert packet[0]["id"] == "sentence-1" and packet[0]["index"] == 0
    assert packet[0]["text"] == output["sentences"][0]["text"]
    citation = packet[0]["citations"][0]
    assert citation["last_verified"] == output["sentences"][0]["citations"][0]["last_verified"]
    assert citation["condition_evidence"][0]["quote"] == "Only the stated synthetic scope applies."
    assert citation["references"][0]["url"] == "https://example.test/policy.pdf"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test/policy.pdf",
        "javascript:alert(1)",
        "data:text/plain,policy",
        "https://secret@example.test/policy.pdf",
        "https://example.test:bad/policy.pdf",
        "https://[malformed",
        "https://exa mple.test/policy.pdf",
        "",
    ],
)
@pytest.mark.parametrize("location", ["citation", "references"])
def test_caption_projection_rejects_invalid_source_urls(output, url, location):
    citation = output["sentences"][0]["citations"][0]
    if location == "citation":
        citation["url"] = url
    else:
        citation["references"][0]["url"] = url
    with pytest.raises(HTTPException) as error:
        reviewed_caption_packet(output)
    assert error.value.status_code == 409


@pytest.mark.parametrize(
    "change", ["expired", "missing_date", "missing_reference", "missing_condition", "unsafe_text"]
)
def test_caption_projection_rejects_incomplete_expired_or_disallowed_content(output, change):
    citation = output["sentences"][0]["citations"][0]
    if change == "expired":
        citation["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    elif change == "missing_date":
        citation.pop("last_verified")
    elif change == "missing_reference":
        citation["references"] = []
    elif change == "missing_condition":
        citation.pop("condition_evidence")
    else:
        output["sentences"][0]["text"] = "You must buy this policy."
    with pytest.raises(HTTPException):
        reviewed_caption_packet(output)


def test_binding_command_cannot_select_report_or_approval_authority():
    base = {"case_id": str(uuid.uuid4()), "idempotency_key": str(uuid.uuid4())}
    valid = BindCaseCommand.model_validate_json(json.dumps(base))
    assert valid.case_id == uuid.UUID(base["case_id"])
    for field in ["owner_id", "report_digest", "turn_id", "release_receipt_id", "approved", "role"]:
        with pytest.raises(ValidationError):
            BindCaseCommand.model_validate_json(json.dumps({**base, field: "synthetic"}))


def test_binding_feature_and_older_schema_stay_closed_by_default():
    settings = Settings(_env_file=None)
    assert settings.voice_case_binding_enabled is False
    assert compatible_schema("015_human_review_requests", settings)
    with pytest.raises(HTTPException):
        VoiceCaseBindingService(None, settings).binding_gate(uuid.uuid4())
    settings.voice_case_binding_enabled = True
    assert not compatible_schema("015_human_review_requests", settings)
    assert not compatible_schema("014_voice_managed", settings)
    assert compatible_schema("016_voice_case_binding", settings)


def test_case_binding_api_requires_auth_closed_body_and_duplicate_key_rejection(monkeypatch):
    settings = Settings(
        _env_file=None,
        auth_provider="legacy_oidc",
        auth_issuer="https://synthetic.test",
        auth_audience="synthetic",
        auth_jwks_url="https://synthetic.test/jwks",
    )
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(api.router)
    client = TestClient(app)
    voice, case, key = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    endpoint = f"/voice/development/sessions/{voice}/case-binding"
    body = {"case_id": str(case), "idempotency_key": str(key)}
    assert client.post(endpoint, json=body).status_code == 401
    assert client.get(endpoint).status_code == 401
    assert client.get(f"/voice/development/sessions/{voice}/captions").status_code == 401
    app.dependency_overrides[security.require_authenticated_user_id] = lambda: uuid.uuid4()
    for field in ["owner_id", "approved", "report_digest", "role", "advisor_id"]:
        assert client.post(endpoint, json={**body, field: "untrusted"}).status_code == 422
    duplicated = f'{{"case_id":"{case}","case_id":"{uuid.uuid4()}","idempotency_key":"{key}"}}'
    assert (
        client.post(
            endpoint, content=duplicated, headers={"content-type": "application/json"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            endpoint, content="{}" * 3000, headers={"content-type": "application/json"}
        ).status_code
        == 413
    )


@pytest.mark.asyncio
async def test_missing_binding_schema_fails_closed_before_voice_read():
    from types import SimpleNamespace

    settings = Settings(
        _env_file=None,
        auth_provider="clerk",
        environment="staging",
        auth_issuer="https://synthetic.test",
        voice_case_binding_enabled=True,
        voice_tools_enabled=True,
    )
    owner = uuid.uuid4()
    settings.voice_test_subjects = [str(owner)]
    service = VoiceCaseBindingService(None, settings)
    service.locked = AsyncMock()
    database = SimpleNamespace(scalar=AsyncMock(return_value=False))
    with pytest.raises(HTTPException) as error:
        await service._context(database, owner, uuid.uuid4())
    assert error.value.status_code == 503
    service.locked.assert_not_awaited()
