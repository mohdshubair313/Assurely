"""Synthetic contracts only. No credentials, microphone or vendor acceptance."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from app.core.config import Settings
from app.voice.billing import test_gate as require_test_gate
from app.voice.evidence import speech_packet
from app.voice.managed import ManagedVoiceService
from app.voice.managed_provider import ManagedVaaniProvider
from app.voice.release import release_status
from app.voice.vaani import VaaniError

AGENT = "00000000-0000-4000-8000-000000000123"


def test_managed_status_urls_are_redacted_in_http_client_logs():
    import logging

    from app.voice.managed_provider import ManagedURLFilter

    record = logging.LogRecord(
        "httpx",
        logging.INFO,
        "",
        0,
        "HTTP %s",
        ("https://api.vaanivoice.ai/api/webrtc/session/status/private-token",),
        None,
    )
    assert ManagedURLFilter().filter(record)
    assert "private-token" not in record.getMessage()


def test_development_api_requires_auth_and_rejects_client_authority(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1.voice_development import router
    from app.core import security
    from app.core.security import require_authenticated_user_id

    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            auth_issuer="https://synthetic.test",
            auth_audience="synthetic",
            auth_jwks_url="https://synthetic.test/jwks",
            auth_provider="legacy_oidc",
        ),
    )

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    assert client.get("/voice/development/availability").status_code == 401
    assert (
        client.post(
            "/voice/development/sessions", json={"idempotency_key": str(uuid.uuid4())}
        ).status_code
        == 401
    )
    app.dependency_overrides[require_authenticated_user_id] = lambda: uuid.uuid4()
    for extra in ["user_id", "agent_id", "role", "fallback"]:
        result = client.post(
            "/voice/development/sessions",
            json={"idempotency_key": str(uuid.uuid4()), extra: "synthetic"},
        )
        assert result.status_code == 422


def test_closed_release_and_development_defaults():
    settings = Settings(_env_file=None)
    with pytest.raises(HTTPException):
        ManagedVoiceService(None, settings).gate(uuid.uuid4())
    with pytest.raises(HTTPException):
        require_test_gate(settings)
    status = release_status(settings)
    assert status["customer_calls_enabled"] is False
    assert status["paid_billing_enabled"] is False
    assert status["synthetic_tests_are_live_acceptance"] is False


@pytest.mark.parametrize(
    "flag",
    [
        "voice_development_enabled",
        "voice_tools_enabled",
        "voice_billing_test_enabled",
        "voice_funded_test_enabled",
    ],
)
def test_additive_schema_compatibility_requires_014_when_feature_enabled(flag):
    from app.db.schema import compatible_schema

    settings = Settings(_env_file=None)
    assert compatible_schema("013_vaani_backend", settings)
    setattr(settings, flag, True)
    assert not compatible_schema("013_vaani_backend", settings)
    assert compatible_schema("014_voice_managed", settings)
    assert not compatible_schema("012_voice_lifecycle", settings)


@pytest.mark.parametrize("key", ["", "rzp_live_synthetic", "rzp_test_synthetic"])
def test_billing_needs_all_explicit_test_configuration(key):
    with pytest.raises(HTTPException):
        require_test_gate(
            Settings(_env_file=None, razorpay_test_key_id=key, voice_billing_test_enabled=True)
        )


def output():
    return {
        "report_status": "ready",
        "sentences": [
            {
                "text": "The fixture requires verification.",
                "citations": [{"source": "Synthetic policy source", "last_verified": "2026-11-01"}],
            }
        ],
    }


def test_speech_keeps_exact_report_sentence_and_citations():
    packet = speech_packet(output())
    assert packet["speech"] == output()["sentences"][0]["text"]
    assert packet["human_approval_granted"] is False
    assert packet["new_calculation"] is False and len(packet["report_digest"]) == 64


@pytest.mark.parametrize("mutation", ["held", "no_date", "future", "expired", "uncited", "sales"])
def test_invalid_report_never_reaches_speech(mutation):
    data = output()
    if mutation == "held":
        data["report_status"] = "held"
    if mutation == "no_date":
        del data["sentences"][0]["citations"][0]["last_verified"]
    if mutation == "future":
        data["sentences"][0]["citations"][0]["last_verified"] = "2099-01-01"
    if mutation == "expired":
        data["sentences"][0]["citations"][0]["expires_at"] = "2020-01-01T00:00:00+00:00"
    if mutation == "uncited":
        data["sentences"][0]["citations"] = []
    if mutation == "sales":
        data["sentences"][0]["text"] = "This is the best policy."
    with pytest.raises(HTTPException):
        speech_packet(data)


@pytest.mark.asyncio
async def test_managed_lifecycle_contract_is_separate_and_explicit_end():
    calls = []

    def handler(request):
        import json

        calls.append(request.url.path)
        body = json.loads(request.content) if request.content else {}
        if request.url.path.endswith("create"):
            assert body["metadata"] == {"assurely_voice_reference": str(reference)}
            return httpx.Response(
                200,
                json={
                    "session_token": "synthetic.session.token.long",
                    "expires_at": (datetime.now(UTC) + timedelta(minutes=2)).isoformat(),
                },
            )
        if request.url.path == "/api/webrtc/session/connect":
            assert body["session_token"] == "synthetic.session.token.long"
            return httpx.Response(
                200,
                json={
                    "lk_url": "wss://livekit.vaanivoice.ai",
                    "lk_token": "synthetic.room.token.long",
                    "room_name": "synthetic_room",
                },
            )
        if request.url.path.endswith("disconnect"):
            assert body["explicit_end"] is True
        return httpx.Response(
            200,
            json={
                "status": "ended" if request.method == "POST" else "created",
                "agent_id": AGENT,
                "room_name": "synthetic_room",
            },
        )

    reference = uuid.uuid4()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = ManagedVaaniProvider(
            Settings(_env_file=None, vaani_api_key="synthetic", vaani_agent_id=AGENT), client
        )
        created = await provider.create(reference, 120)
        assert "synthetic.session" not in repr(created)
        await provider.status(created.session_token)
        await provider.connect(created.session_token)
        await provider.terminate(created.session_token)
    assert calls[0] == "/api/webrtc/session/create" and len(calls) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["host", "room", "token", "end"])
async def test_managed_adapter_rejects_untrusted_material_or_unconfirmed_end(mode):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "lk_url": "wss://evil.example"
                    if mode == "host"
                    else "wss://livekit.vaanivoice.ai",
                    "lk_token": "short" if mode == "token" else "synthetic.long.room.token",
                    "room_name": "room/evil" if mode == "room" else "room",
                    "status": "active",
                    "agent_id": AGENT,
                },
            )
        )
    ) as client:
        provider = ManagedVaaniProvider(
            Settings(_env_file=None, vaani_api_key="synthetic", vaani_agent_id=AGENT), client
        )
        with pytest.raises(VaaniError):
            await (
                provider.terminate(SecretStr("synthetic.long.token"))
                if mode == "end"
                else provider.connect(SecretStr("synthetic.long.token"))
            )
