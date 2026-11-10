"""Real disposable PostgreSQL transactions with fake external provider responses."""

import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import func, insert, select, update

from app.core.config import Settings
from app.core.consent import VOICE_CONSENT_VERSION
from app.models.db.auth_identity import AuthIdentity
from app.models.db.consent_record import ConsentRecord
from app.models.db.user import User
from app.models.db.voice import VoiceEntitlement, VoiceSession, VoiceUsageLedger
from app.models.db.voice_lifecycle import (
    VoiceFundingAllocation,
    VoiceFundingPeriod,
    VoiceManagedOperation,
    VoiceSubscription,
)
from app.voice.billing import TestBillingService as BillingService
from app.voice.events import process_events, receive_event
from app.voice.managed import ManagedVoiceService
from app.voice.managed_provider import ManagedConnection, ManagedSession, ManagedStatus
from app.voice.vaani import VaaniError
from tests.integration.test_clerk_identity import URL as TEST_DATABASE_URL
from tests.integration.test_clerk_identity import database  # noqa: F401

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="Explicit disposable database required"
)


class Provider:
    def __init__(self, agent):
        self.agent, self.room = agent, "synthetic_" + uuid.uuid4().hex
        self.created = self.connected = self.ended = 0
        self.fail = None

    async def create(self, reference, cap):
        self.created += 1
        if self.fail == "create":
            raise VaaniError("uncertain_transport")
        return ManagedSession(
            session_token="synthetic.session.long.token",
            expires_at=datetime.now(UTC) + timedelta(seconds=cap),
        )

    async def status(self, token):
        return ManagedStatus(status="created", room_name=self.room, agent_id=self.agent)

    async def connect(self, token):
        self.connected += 1
        if self.fail == "connect":
            raise VaaniError("uncertain_transport")
        return ManagedConnection(
            lk_url="wss://livekit.vaanivoice.ai",
            lk_token="synthetic.long.room.token",
            room_name=self.room,
        )

    async def terminate(self, token):
        self.ended += 1
        return ManagedStatus(status="ended", room_name=self.room, agent_id=self.agent)


@pytest.fixture
def setup(database):  # noqa: F811 - imported pytest fixture dependency
    engine, factory = database
    owner, agent = uuid.uuid4(), uuid.uuid4()
    settings = Settings(
        _env_file=None,
        environment="development",
        auth_issuer="https://synthetic.clerk.test",
        voice_development_enabled=True,
        vaani_dispatch_enabled=True,
        vaani_byol_enabled=True,
        vaani_ingress_enabled=True,
        vaani_dev_agent_reviewed=True,
        vaani_agent_id=str(agent),
        vaani_api_key="synthetic-private-key",
        vaani_byol_token="synthetic-byol-" + "b" * 40,
        vaani_staging_base_url="https://synthetic.trycloudflare.com",
        vaani_webhook_secret="synthetic-webhook-" + "s" * 40,
        voice_test_subjects=[str(owner)],
        voice_token_encryption_key=Fernet.generate_key().decode(),
        voice_max_call_seconds=120,
        voice_billing_test_enabled=True,
        razorpay_test_key_id="rzp_test_synthetic",
        razorpay_test_key_secret="synthetic",
        razorpay_test_webhook_secret="s" * 40,
        voice_test_plan_id="plan_synthetic",
        voice_test_plan_seconds=900,
    )
    with engine.begin() as db:
        db.execute(insert(User).values(id=owner, role="customer"))
        db.execute(
            insert(AuthIdentity).values(
                id=uuid.uuid4(),
                provider="clerk",
                issuer=settings.auth_issuer,
                subject="synthetic_" + owner.hex,
                user_id=owner,
                disabled=False,
            )
        )
        for scope in ("voice_microphone", "voice_vendor_processing"):
            db.execute(
                insert(ConsentRecord).values(
                    user_id=owner, scope=scope, purpose_version=VOICE_CONSENT_VERSION
                )
            )
    provider = Provider(agent)
    return (
        engine,
        factory,
        settings,
        owner,
        provider,
        ManagedVoiceService(factory, settings, provider),
    )


async def connected(setup):
    _, _, _, owner, provider, service = setup
    session, _ = await service.reserve(owner, uuid.uuid4())
    await service.advance(owner, session.id)
    await service.advance(owner, session.id)
    # Server-owned binding exists before connect can dispatch the agent.
    assert (await service.view(owner, session.id))["phase"] == "ready"
    await service.advance(owner, session.id, connect=True)
    return session


def test_concurrent_reservations_and_operation_claims(setup):
    engine, factory, settings, owner, provider, service = setup
    key = uuid.uuid4()

    async def reserve_parallel():
        return await asyncio.wait_for(
            asyncio.gather(*(service.reserve(owner, key) for _ in range(4))), timeout=15
        )

    values = asyncio.run(reserve_parallel())
    assert len({row.id for row, _ in values}) == 1
    assert sum(created for _, created in values) == 1
    session = values[0][0]

    async def advance():
        await asyncio.gather(*(service.advance(owner, session.id) for _ in range(4)))

    asyncio.run(advance())
    assert provider.created == 1
    with engine.connect() as db:
        ent = db.execute(select(VoiceEntitlement).where(VoiceEntitlement.user_id == owner)).one()
        assert ent.reserved_seconds == 120
        op = db.execute(
            select(VoiceManagedOperation).where(VoiceManagedOperation.session_id == session.id)
        ).one()
        assert "synthetic.session.long.token" not in (op.encrypted_token or "")


def test_connect_retry_same_session_and_terminal_event_settles_once(setup):
    engine, factory, settings, owner, provider, service = setup

    async def run():
        session = await connected(setup)
        await service.advance(owner, session.id, connect=True)
        assert provider.created == provider.connected == 1
        assert (await service.view(owner, session.id, material=True))["allowed"] is True
        await service.request_end(owner, session.id)
        await service.advance(owner, session.id)
        assert provider.ended == 1
        view = await service.view(owner, session.id)
        assert (
            not view["allowed"]
            and view["reserved_seconds"] == 120
            and view["consumed_seconds"] == 0
        )
        raw = json.dumps(
            {
                "event": "call_ended",
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {"room_name": provider.room, "call_duration": "12.125"},
            }
        ).encode()
        sig = hmac.new(
            settings.vaani_webhook_secret.get_secret_value().encode(), raw, hashlib.sha256
        ).hexdigest()
        assert await receive_event(factory, settings, raw, sig) is False
        assert await receive_event(factory, settings, raw, sig) is True
        await process_events(factory, settings)
        await process_events(factory, settings)
        await service.advance(owner, session.id)
        assert (await service.view(owner, session.id))["consumed_seconds"] == 13
        return session.id

    session_id = asyncio.run(run())
    with engine.connect() as db:
        entries = db.execute(
            select(VoiceUsageLedger.entry_type, VoiceUsageLedger.seconds).where(
                VoiceUsageLedger.session_id == session_id
            )
        ).all()
        assert sorted(entries) == [("release", 107), ("reservation", 120), ("settlement", 13)]


@pytest.mark.parametrize("failure", ["create", "connect"])
def test_uncertain_start_is_durable_and_never_redispatched(setup, failure):
    engine, _, _, owner, provider, service = setup

    async def run():
        session, _ = await service.reserve(owner, uuid.uuid4())
        if failure == "connect":
            await service.advance(owner, session.id)
            await service.advance(owner, session.id)
        provider.fail = failure
        await service.advance(owner, session.id, connect=True)
        with engine.begin() as db:
            db.execute(
                update(VoiceManagedOperation)
                .where(VoiceManagedOperation.session_id == session.id)
                .values(lease_until=datetime.now(UTC) - timedelta(seconds=2))
            )
        # New service object models restart; persisted operation prevents another creation/connect.
        restarted = ManagedVoiceService(service.factory, service.settings, provider)
        await restarted.advance(owner, session.id, connect=True)
        return await restarted.view(owner, session.id)

    view = asyncio.run(run())
    assert provider.created == 1 and provider.connected == (failure == "connect")
    assert view["phase"] == "start_unknown" and view["consumed_seconds"] == 0
    with engine.connect() as db:
        assert (
            db.scalar(
                select(VoiceEntitlement.reserved_seconds).where(VoiceEntitlement.user_id == owner)
            )
            == 120
        )


def test_consent_revocation_and_cross_owner_block_material_without_refund(setup):
    engine, _, _, owner, provider, service = setup

    async def run():
        session = await connected(setup)
        with pytest.raises(HTTPException) as error:
            await service.view(uuid.uuid4(), session.id, material=True)
        assert error.value.status_code == 404
        with engine.begin() as db:
            db.execute(
                update(ConsentRecord)
                .where(ConsentRecord.user_id == owner)
                .values(revoked_at=datetime.now(UTC))
            )
        assert not (await service.view(owner, session.id))["allowed"]
        await service.advance(owner, session.id)
        assert provider.ended == 1
        assert (await service.view(owner, session.id))["consumed_seconds"] == 0

    asyncio.run(run())


def test_expiry_before_dispatch_releases_only_known_no_call_reservation(setup):
    engine, _, _, owner, provider, service = setup

    async def run():
        session, _ = await service.reserve(owner, uuid.uuid4())
        with engine.begin() as db:
            db.execute(
                update(VoiceSession)
                .where(VoiceSession.id == session.id)
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=2))
            )
        await service.advance(owner, session.id)
        return await service.view(owner, session.id)

    view = asyncio.run(run())
    assert provider.created == 0 and view["state"] == "failed"
    with engine.connect() as db:
        assert (
            db.scalar(
                select(VoiceEntitlement.reserved_seconds).where(VoiceEntitlement.user_id == owner)
            )
            == 0
        )


def test_stale_creating_lease_after_process_restart_does_not_retry(setup):
    engine, _, _, owner, provider, service = setup

    async def run():
        session, _ = await service.reserve(owner, uuid.uuid4())
        with engine.begin() as db:
            db.execute(
                update(VoiceManagedOperation)
                .where(VoiceManagedOperation.session_id == session.id)
                .values(phase="creating", lease_until=datetime.now(UTC) - timedelta(seconds=2))
            )
        await service.advance(owner, session.id)
        assert (await service.view(owner, session.id))["phase"] == "start_unknown"

    asyncio.run(run())
    assert provider.created == 0


def billing_event(setup, event="subscription.charged", stamp=None):
    _, _, settings, _, _, _ = setup
    now = int(datetime.now(UTC).timestamp())
    raw = json.dumps(
        {
            "event": event,
            "created_at": stamp or now,
            "payload": {
                "subscription": {
                    "entity": {
                        "id": "sub_" + setup[3].hex,
                        "plan_id": settings.voice_test_plan_id,
                        "current_start": now - 60,
                        "current_end": now + 3600,
                    }
                },
                "payment": {"entity": {"status": "captured", "captured": True}},
            },
        }
    ).encode()
    return raw, hmac.new(
        settings.razorpay_test_webhook_secret.get_secret_value().encode(), raw, hashlib.sha256
    ).hexdigest()


def test_signed_billing_deduplicates_periods_and_does_not_fund_runtime(setup):
    engine, factory, settings, owner, _, service = setup
    asyncio.run(service.reserve(owner, uuid.uuid4()))
    with engine.begin() as db:
        db.execute(
            insert(VoiceSubscription).values(
                id="pending_" + owner.hex,
                user_id=owner,
                request_key=uuid.uuid4(),
                plan_id=settings.voice_test_plan_id,
                external_id="sub_" + setup[3].hex,
                included_seconds=settings.voice_test_plan_seconds,
                status="created",
            )
        )
    billing = BillingService(factory, settings)
    raw, sig = billing_event(setup)

    async def run():
        with pytest.raises(HTTPException):
            await billing.receive(raw, "0" * 64, "bad")
        assert not (await billing.receive(raw, sig, "event_synthetic"))["duplicate"]
        assert (await billing.receive(raw, sig, "event_synthetic"))["duplicate"]
        changed = raw + b" "
        changed_sig = hmac.new(
            settings.razorpay_test_webhook_secret.get_secret_value().encode(),
            changed,
            hashlib.sha256,
        ).hexdigest()
        with pytest.raises(HTTPException) as conflict:
            await billing.receive(changed, changed_sig, "event_synthetic")
        assert conflict.value.status_code == 409

    asyncio.run(run())
    with engine.connect() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(VoiceFundingPeriod)
                .where(VoiceFundingPeriod.user_id == owner)
            )
            == 1
        )
        assert (
            db.scalar(
                select(VoiceEntitlement.included_seconds).where(VoiceEntitlement.user_id == owner)
            )
            == 900
        )


def test_missing_consent_and_conflicting_start_key_never_dispatch(setup):
    engine, factory, settings, owner, provider, service = setup

    async def run():
        session, _ = await service.reserve(owner, uuid.uuid4())
        # A mock receipt with the same owner/key has different normalized inputs.
        from app.voice.service import VoiceSessionService

        settings.voice_provider = "mock"
        with engine.begin() as db:
            db.execute(
                insert(ConsentRecord).values(
                    user_id=owner, scope="voice_demo", purpose_version=VOICE_CONSENT_VERSION
                )
            )
        with pytest.raises(HTTPException) as conflict:
            await VoiceSessionService(factory, settings).start(owner, "en", session.idempotency_key)
        assert conflict.value.status_code == 409
        with engine.begin() as db:
            db.execute(
                update(ConsentRecord)
                .where(ConsentRecord.user_id == owner)
                .values(revoked_at=datetime.now(UTC))
            )
        with pytest.raises(HTTPException) as denied:
            await service.reserve(owner, uuid.uuid4())
        assert denied.value.status_code == 403

    asyncio.run(run())
    assert provider.created == 0


def test_simultaneous_end_and_connect_preserve_reservation_until_signed_end(setup):
    engine, _, _, owner, provider, service = setup

    async def run():
        session, _ = await service.reserve(owner, uuid.uuid4())
        await service.advance(owner, session.id)
        await service.advance(owner, session.id)
        await asyncio.gather(
            service.advance(owner, session.id, connect=True), service.request_end(owner, session.id)
        )
        await service.advance(owner, session.id)
        view = await service.view(owner, session.id)
        assert not view["allowed"] and view["end_requested"]
        assert view["consumed_seconds"] == 0

    asyncio.run(run())
    assert provider.created == 1 and provider.connected <= 1
    with engine.connect() as db:
        assert (
            db.scalar(
                select(VoiceEntitlement.reserved_seconds).where(VoiceEntitlement.user_id == owner)
            )
            == 120
        )


def test_provider_deadline_requests_hard_end_without_local_refund(setup):
    engine, _, _, owner, provider, service = setup

    async def run():
        session = await connected(setup)
        with engine.begin() as db:
            db.execute(
                update(VoiceSession)
                .where(VoiceSession.id == session.id)
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
        await service.advance(owner, session.id)
        assert provider.ended == 1
        assert (await service.view(owner, session.id))["phase"] == "awaiting_usage"

    asyncio.run(run())
    with engine.connect() as db:
        assert (
            db.scalar(
                select(VoiceEntitlement.reserved_seconds).where(VoiceEntitlement.user_id == owner)
            )
            == 120
        )


def test_checkout_timeout_is_not_retried_and_live_keys_are_rejected(setup):
    import httpx

    engine, factory, settings, owner, _, _ = setup
    billing = BillingService(factory, settings)
    calls = []

    def transport(request):
        calls.append(request)
        raise httpx.ReadTimeout("synthetic private response", request=request)

    async def run():
        key = uuid.uuid4()
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            with pytest.raises(HTTPException):
                await billing.checkout(owner, key, client)
            with pytest.raises(HTTPException) as retry:
                await billing.checkout(owner, key, client)
            assert retry.value.status_code == 409
            settings.razorpay_test_key_id = "rzp_live_synthetic"
            with pytest.raises(HTTPException) as denied:
                await billing.checkout(owner, uuid.uuid4(), client)
            assert denied.value.status_code == 503

    asyncio.run(run())
    assert len(calls) == 1


def test_recap_encryption_consent_fresh_evidence_and_retention(setup, monkeypatch):
    from app.models.db.session import Session
    from app.models.db.voice_lifecycle import VoiceRecap
    from app.voice import recaps
    from app.voice.recaps import RecapService, prune_recaps

    engine, factory, settings, owner, _, _ = setup
    settings.voice_tools_enabled = True
    case_id = uuid.uuid4()
    with engine.begin() as db:
        db.execute(insert(Session).values(id=case_id, user_id=owner, intent="health"))
        db.execute(
            insert(ConsentRecord).values(
                user_id=owner, scope="voice_summary", purpose_version=VOICE_CONSENT_VERSION
            )
        )
    packet = {
        "case_id": str(case_id),
        "report_digest": "a" * 64,
        "speech": "Synthetic report excerpt",
    }

    async def current(*args):
        return packet.copy()

    monkeypatch.setattr(recaps, "current_packet", current)
    svc = RecapService(factory, settings)

    async def run():
        receipt = await svc.create_recap(owner, case_id, uuid.uuid4())
        recap_id = uuid.UUID(receipt["recap_id"])
        with engine.connect() as db:
            encrypted = db.scalar(
                select(VoiceRecap.encrypted_content).where(VoiceRecap.id == recap_id)
            )
            assert "Synthetic report excerpt" not in encrypted
        assert (await svc.read_recap(owner, recap_id))["speech"] == packet["speech"]
        packet["report_digest"] = "b" * 64
        with pytest.raises(HTTPException) as changed:
            await svc.read_recap(owner, recap_id)
        assert changed.value.status_code == 409
        with engine.begin() as db:
            db.execute(
                update(ConsentRecord)
                .where(ConsentRecord.user_id == owner, ConsentRecord.scope == "voice_summary")
                .values(revoked_at=datetime.now(UTC))
            )
        with pytest.raises(HTTPException):
            await svc.read_recap(owner, recap_id)
        await prune_recaps(factory)
        with engine.connect() as db:
            assert (
                db.scalar(select(VoiceRecap.encrypted_content).where(VoiceRecap.id == recap_id))
                is None
            )

    asyncio.run(run())


def test_case_follow_up_reuses_existing_pipeline_and_holds_all_speech(setup, monkeypatch):
    from starlette.requests import Request

    from app.api.v1 import message
    from app.core.consent import CONSENT_VERSION
    from app.models.db.session import Session
    from app.voice.evidence import case_turn

    engine, factory, settings, owner, _, _ = setup
    case_id = uuid.uuid4()
    settings.voice_tools_enabled = True
    with engine.begin() as db:
        db.execute(insert(Session).values(id=case_id, user_id=owner, intent="health"))
        db.execute(
            insert(ConsentRecord).values(
                user_id=owner, scope="process_comparison", purpose_version=CONSENT_VERSION
            )
        )
    calls = []

    async def send(req, request, authenticated_user_id):
        calls.append((req.session_id, req.user_message, authenticated_user_id))
        return message.MessageResponse(
            session_id=str(case_id), reply="Internal draft must not escape", delivery_hold=True
        )

    monkeypatch.setattr(message, "send_message", send)

    async def run():
        request = Request({"type": "http", "method": "POST", "path": "/synthetic"})
        result = await case_turn(factory, settings, owner, case_id, "Explain the clause", request)
        assert result["delivery_hold"] and result["sentences"] == []
        assert "Internal draft" not in json.dumps(result)
        with pytest.raises(HTTPException) as forbidden:
            await case_turn(factory, settings, uuid.uuid4(), case_id, "Explain the clause", request)
        assert forbidden.value.status_code == 404

    asyncio.run(run())
    assert calls == [(str(case_id), "Explain the clause", owner)]


def test_funded_period_cap_releases_known_unused_seconds_without_reset(setup):
    engine, _, settings, owner, _, service = setup
    settings.voice_funded_test_enabled = True
    period_id = uuid.uuid4()
    now = datetime.now(UTC)
    with engine.begin() as db:
        db.execute(
            insert(VoiceSubscription).values(
                id="pending_" + owner.hex,
                user_id=owner,
                request_key=uuid.uuid4(),
                plan_id=settings.voice_test_plan_id,
                included_seconds=180,
                external_id="sub_" + owner.hex,
                status="active",
            )
        )
        db.execute(
            insert(VoiceFundingPeriod).values(
                id=period_id,
                user_id=owner,
                subscription_id="sub_" + owner.hex,
                plan_id=settings.voice_test_plan_id,
                period_start=now - timedelta(seconds=1),
                period_end=now + timedelta(hours=1),
                included_seconds=180,
                status="funded_test",
            )
        )

    async def run():
        session, _ = await service.reserve(owner, uuid.uuid4())
        with pytest.raises(HTTPException) as exhausted:
            await service.reserve(owner, uuid.uuid4())
        assert exhausted.value.status_code == 402
        await service.request_end(owner, session.id)
        await service.advance(owner, session.id)  # pending create: confirmed no external call
        await service.reserve(owner, uuid.uuid4())

    asyncio.run(run())
    with engine.connect() as db:
        assert (
            db.scalar(
                select(VoiceEntitlement.included_seconds).where(VoiceEntitlement.user_id == owner)
            )
            == 1080
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(VoiceFundingAllocation)
                .where(VoiceFundingAllocation.period_id == period_id)
            )
            == 2
        )
    from sqlalchemy.exc import DBAPIError

    from tests.integration.test_clerk_identity import OLD

    # Even privileged SQL cannot attach another owner's legacy session to this period.
    with pytest.raises(DBAPIError), engine.begin() as db:
        db.execute(insert(VoiceFundingAllocation).values(session_id=OLD, period_id=period_id))
    with pytest.raises(DBAPIError), engine.begin() as db:
        db.execute(
            update(VoiceFundingPeriod)
            .where(VoiceFundingPeriod.id == period_id)
            .values(status="funded_test")
        )


def test_period_rollover_preserves_original_inflight_funding(setup, monkeypatch):
    engine, _, settings, owner, _, service = setup
    settings.voice_funded_test_enabled = True
    settings.voice_max_concurrent_calls = 2
    now = datetime.now(UTC)
    periods = [uuid.uuid4(), uuid.uuid4()]
    with engine.begin() as db:
        db.execute(
            insert(VoiceSubscription).values(
                id="pending_" + owner.hex,
                user_id=owner,
                request_key=uuid.uuid4(),
                plan_id=settings.voice_test_plan_id,
                included_seconds=180,
                external_id="sub_" + owner.hex,
                status="active",
            )
        )
        for index, period in enumerate(periods):
            db.execute(
                insert(VoiceFundingPeriod).values(
                    id=period,
                    user_id=owner,
                    subscription_id="sub_" + owner.hex,
                    plan_id=settings.voice_test_plan_id,
                    period_start=now + timedelta(seconds=-1 if index == 0 else 30),
                    period_end=now + timedelta(seconds=30 if index == 0 else 3600),
                    included_seconds=180,
                    status="funded_test",
                )
            )

    async def run():
        first = await connected(setup)

        async def later(db):
            return now + timedelta(seconds=60)

        monkeypatch.setattr(service, "now", later)
        second, _ = await service.reserve(owner, uuid.uuid4())
        return first.id, second.id

    first, second = asyncio.run(run())
    with engine.connect() as db:
        assert (
            db.scalar(
                select(VoiceFundingAllocation.period_id).where(
                    VoiceFundingAllocation.session_id == first
                )
            )
            == periods[0]
        )
        assert (
            db.scalar(
                select(VoiceFundingAllocation.period_id).where(
                    VoiceFundingAllocation.session_id == second
                )
            )
            == periods[1]
        )
        assert (
            db.scalar(
                select(VoiceEntitlement.reserved_seconds).where(VoiceEntitlement.user_id == owner)
            )
            == 240
        )
