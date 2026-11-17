"""Actual PostgreSQL recap authority; media and provider interactions are synthetic."""

import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import func, select, update

from app.core.consent import VOICE_CONSENT_VERSION
from app.db import advisor_review, human_review, policy_publication_store, report_release
from app.models.db.auth_identity import AuthIdentity
from app.models.db.consent_record import ConsentRecord
from app.models.db.policy_publication import PolicyPublicationEvent
from app.models.db.voice import VoiceEntitlement, VoiceUsageLedger
from app.models.db.voice_byol_turn import VoiceByolTurn
from app.models.db.voice_lifecycle import VoiceRecap
from tests.integration.test_advisor_review import decide
from tests.integration.test_byol_evidence_bridge import prepare, turn
from tests.integration.test_byol_evidence_bridge import setup as _bridge_setup
from tests.integration.test_policy_publication_workflow import decide as publication_decide
from tests.integration.test_policy_review_workflow import ACTOR, URL
from tests.integration.test_voice_case_binding import database as _database
from tests.integration.test_voice_case_binding import publication_input as _publication_input
from tests.integration.test_voice_case_binding import setup as _case_setup

database = _database
publication_input = _publication_input
case_setup = _case_setup
bridge_setup = _bridge_setup
pytestmark = pytest.mark.skipif(not URL, reason="Dedicated synthetic PostgreSQL required")


@pytest_asyncio.fixture
async def setup(bridge_setup):
    from app.voice.activity import ActivityRecapService

    value = bridge_setup
    async with value.factory() as db, db.begin():
        db.add(
            ConsentRecord(
                user_id=value.owner, scope="voice_summary", purpose_version=VOICE_CONSENT_VERSION
            )
        )
    value.activity = ActivityRecapService(value.factory, value.settings)
    return value


async def sent(setup, response_id=1, content="Read my reviewed report."):
    ticket, answer = await prepare(setup, turn(setup, response_id, content))
    await setup.bridge.authorize_send(answer)
    assert await setup.bridge.complete(ticket)
    return ticket


async def read(setup):
    return await setup.activity.read_activity(setup.owner, setup.voice.id)


async def finances(setup):
    async with setup.factory() as db:
        row = await db.scalar(
            select(VoiceEntitlement).where(VoiceEntitlement.user_id == setup.owner)
        )
        ledger = (
            await db.execute(
                select(VoiceUsageLedger.entry_type, VoiceUsageLedger.seconds).where(
                    VoiceUsageLedger.session_id == setup.voice.id
                )
            )
        ).all()
        return row.included_seconds, row.reserved_seconds, row.consumed_seconds, ledger


async def test_empty_activity_has_no_report_or_persisted_summary(setup):
    before = await finances(setup)
    value = await read(setup)
    assert value["kind"] == "voice_session_activity_recap"
    assert value["voice_session_id"] == str(setup.voice.id)
    assert value["events"] == []
    assert value["reviewed_report"] is None and value["report_availability"] == "not_sent"
    assert value["transcript_stored"] is False and value["audio_delivery_verified"] is False
    assert await finances(setup) == before
    async with setup.factory() as db:
        assert await db.scalar(select(func.count()).select_from(VoiceRecap)) == 0


async def test_recap_preserves_complete_report_and_dated_references_with_short_lease(setup):
    await sent(setup)
    before = await finances(setup)
    value = await read(setup)
    assert value["events"][0]["status"] == "response_sent"
    assert value["events"][0]["answer_kind"] == "report"
    assert value["report_availability"] == "available"
    report = value["reviewed_report"]
    assert report["case_id"] == str(setup.case_id)
    assert report["report_digest"] == setup.command.report_digest
    assert [s["text"] for s in report["sentences"]] == [
        s["text"] for s in setup.state["output"]["sentences"]
    ]
    assert all(
        c["references"] and c["last_verified"] for s in report["sentences"] for c in s["citations"]
    )
    now = datetime.now(UTC)
    assert 0 < (datetime.fromisoformat(value["display_expires_at"]) - now).total_seconds() <= 10
    assert datetime.fromisoformat(report["display_expires_at"]) <= datetime.fromisoformat(
        value["display_expires_at"]
    )
    assert "PRIVATE_CHAT" not in json.dumps(value) and "PRIVATE_PROFILE" not in json.dumps(value)
    assert "synthetic.long.room.token" not in json.dumps(value)
    assert await finances(setup) == before


async def test_recap_distinguishes_sent_unknown_operational_interrupted_failed_pending(setup):
    await sent(setup, 1)
    _, answer = await prepare(setup, turn(setup, 2))
    await setup.bridge.authorize_send(answer)
    await sent(setup, 3, "PRIVATE_MEDICAL_QUESTION never save this")
    old = await setup.bridge.begin(setup.provider.room, setup.connection, turn(setup, 4))
    assert old is not None
    failed = await setup.bridge.begin(setup.provider.room, setup.connection, turn(setup, 5))
    async with setup.factory() as db, db.begin():
        await db.execute(
            update(VoiceByolTurn)
            .where(VoiceByolTurn.id == failed.id)
            .values(state="failed")
        )
    await setup.bridge.begin(setup.provider.room, setup.connection, turn(setup, 6))
    value = await read(setup)
    assert [(e["response_id"], e["status"]) for e in value["events"]] == [
        (1, "response_sent"),
        (2, "delivery_uncertain"),
        (3, "response_sent"),
        (4, "interrupted"),
        (5, "failed"),
        (6, "pending"),
    ]
    assert value["events"][2]["intent"] == "unsupported"
    assert value["events"][2]["answer_kind"] == "operational"
    assert "PRIVATE_MEDICAL_QUESTION" not in json.dumps(value)
    assert value["audio_delivery_verified"] is False


@pytest.mark.parametrize("phase", ["prepared", "send_unknown", "operational_sent"])
async def test_unconfirmed_or_operational_responses_do_not_imply_report_was_sent(setup, phase):
    ticket, answer = await prepare(
        setup,
        turn(
            setup,
            content=(
                "Unsupported private request" if phase == "operational_sent" else "Read my report."
            ),
        ),
    )
    if phase != "prepared":
        await setup.bridge.authorize_send(answer)
    if phase == "operational_sent":
        assert await setup.bridge.complete(ticket)
    value = await read(setup)
    assert value["reviewed_report"] is None
    assert value["report_availability"] == "not_sent"


@pytest.mark.parametrize("scope", ["voice_summary", "process_comparison"])
@pytest.mark.parametrize("change", ["missing", "revoked", "stale"])
async def test_current_separate_summary_and_processing_consents_are_required(setup, scope, change):
    await sent(setup)
    async with setup.factory() as db, db.begin():
        row = await db.scalar(
            select(ConsentRecord).where(
                ConsentRecord.user_id == setup.owner, ConsentRecord.scope == scope
            )
        )
        if change == "missing":
            await db.delete(row)
        elif change == "revoked":
            row.revoked_at = datetime.now(UTC)
        else:
            row.purpose_version = "obsolete-synthetic-purpose"
    with pytest.raises(HTTPException) as error:
        await read(setup)
    assert error.value.status_code == 403


async def test_cross_owner_unknown_session_and_disabled_identity_are_denied(setup):
    await sent(setup)
    for owner, session in [(uuid.uuid4(), setup.voice.id), (setup.owner, uuid.uuid4())]:
        with pytest.raises(HTTPException) as error:
            await setup.activity.read_activity(owner, session)
        assert error.value.status_code in {403, 404, 503}
    async with setup.factory() as db, db.begin():
        await db.execute(
            update(AuthIdentity).where(AuthIdentity.user_id == setup.owner).values(disabled=True)
        )
    with pytest.raises(HTTPException) as error:
        await read(setup)
    assert error.value.status_code == 403


@pytest.mark.parametrize(
    "mutation", ["human_revoke", "new_human_request", "new_turn", "source_revoke"]
)
async def test_current_holds_remove_report_but_preserve_truthful_activity(setup, mutation):
    await sent(setup)
    if mutation == "human_revoke":
        await decide(
            setup.factory,
            setup.command.report_digest,
            advisor_review.DecisionCommand(
                request_key=uuid.uuid4(),
                expected_revision=1,
                action="revoke",
                reason="Synthetic independent human withdrawal",
            ),
        )
    elif mutation == "new_human_request":
        async with setup.factory() as db, db.begin():
            await human_review.create(
                db,
                ACTOR.issuer,
                setup.case_id,
                setup.owner,
                human_review.RequestCommand(request_key=uuid.uuid4()),
            )
    elif mutation == "new_turn":
        async with setup.factory() as db, db.begin():
            await report_release.begin_turn(db, ACTOR.issuer, str(setup.case_id), setup.owner)
    else:
        async with setup.factory() as db:
            event = await db.scalar(
                select(PolicyPublicationEvent).where(PolicyPublicationEvent.action == "publish")
            )
        await publication_decide(
            setup.factory,
            event.publication_digest,
            policy_publication_store.PublishCommand(
                request_key=uuid.uuid4(),
                expected_revision=event.revision,
                representation_event_id=event.representation_event_id,
                action="revoke",
                reason="Synthetic source withdrawal",
            ),
        )
    value = await read(setup)
    assert value["report_availability"] == "unavailable" and value["reviewed_report"] is None
    assert value["events"][0]["status"] == "response_sent"
    assert all(s["text"] not in json.dumps(value) for s in setup.state["output"]["sentences"])


async def test_recreated_service_recovers_receipts_without_redispatch(setup):
    from app.voice.activity import ActivityRecapService

    await sent(setup)
    await setup.engine.dispose()
    setup.activity = ActivityRecapService(setup.factory, setup.settings)
    value = await read(setup)
    assert len(value["events"]) == 1 and value["report_availability"] == "available"
    assert setup.provider.created == setup.provider.connected == 1


async def test_ended_session_recap_does_not_require_microphone_or_live_session(setup):
    from app.voice.events import process_events, receive_event

    await sent(setup)
    await setup.managed.request_end(setup.owner, setup.voice.id)
    await setup.managed.advance(setup.owner, setup.voice.id)
    raw = json.dumps(
        {
            "event": "call_ended",
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {"room_name": setup.provider.room, "call_duration": "12.125"},
        }
    ).encode()
    signature = hmac.new(
        setup.settings.vaani_webhook_secret.get_secret_value().encode(), raw, hashlib.sha256
    ).hexdigest()
    await receive_event(setup.factory, setup.settings, raw, signature)
    await process_events(setup.factory, setup.settings)
    async with setup.factory() as db, db.begin():
        await db.execute(
            update(ConsentRecord)
            .where(
                ConsentRecord.user_id == setup.owner,
                ConsentRecord.scope.in_(
                    ["voice_microphone", "voice_vendor_processing", "voice_report_speech"]
                ),
            )
            .values(revoked_at=datetime.now(UTC))
        )
    before = await finances(setup)
    value = await read(setup)
    assert value["session_state"] == "ended" and value["report_availability"] == "available"
    assert value["audio_delivery_verified"] is False
    assert await finances(setup) == before


async def test_concurrent_reads_preserve_receipts_and_usage(setup):
    await sent(setup)
    before = await finances(setup)
    values = await asyncio.wait_for(asyncio.gather(*(read(setup) for _ in range(4))), 25)
    assert all(v["events"] == values[0]["events"] for v in values)
    assert await finances(setup) == before


async def test_legacy_recap_same_key_deleted_and_expired_content_cannot_be_resurrected(setup):
    from app.voice.recaps import RecapService

    service = RecapService(setup.factory, setup.settings)
    key = uuid.uuid4()
    first = await service.create_recap(setup.owner, setup.case_id, key)
    assert await service.create_recap(setup.owner, setup.case_id, key) == first
    recap_id = uuid.UUID(first["recap_id"])
    assert (await service.read_recap(setup.owner, recap_id))["kind"] == "validated_report_excerpt"
    await service.delete_recap(setup.owner, recap_id)
    for method in [
        lambda: service.create_recap(setup.owner, setup.case_id, key),
        lambda: service.read_recap(setup.owner, recap_id),
    ]:
        with pytest.raises(HTTPException) as error:
            await method()
        assert error.value.status_code == 404
    second_key = uuid.uuid4()
    second = await service.create_recap(setup.owner, setup.case_id, second_key)
    async with setup.factory() as db, db.begin():
        await db.execute(
            update(VoiceRecap)
            .where(VoiceRecap.id == uuid.UUID(second["recap_id"]))
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    with pytest.raises(HTTPException) as error:
        await service.create_recap(setup.owner, setup.case_id, second_key)
    assert error.value.status_code == 404


async def test_legacy_recap_fresh_human_hold_blocks_retry_and_read(setup):
    from app.voice.recaps import RecapService

    service = RecapService(setup.factory, setup.settings)
    key = uuid.uuid4()
    first = await service.create_recap(setup.owner, setup.case_id, key)
    async with setup.factory() as db, db.begin():
        await human_review.create(
            db,
            ACTOR.issuer,
            setup.case_id,
            setup.owner,
            human_review.RequestCommand(request_key=uuid.uuid4()),
        )
    for method in [
        lambda: service.create_recap(setup.owner, setup.case_id, key),
        lambda: service.read_recap(setup.owner, uuid.UUID(first["recap_id"])),
    ]:
        with pytest.raises(HTTPException) as error:
            await method()
        assert error.value.status_code == 409


async def test_legacy_read_waiting_on_mutation_cannot_return_deleted_excerpt(setup):
    from app.voice.recaps import RecapService

    service = RecapService(setup.factory, setup.settings)
    receipt = await service.create_recap(setup.owner, setup.case_id, uuid.uuid4())
    recap_id = uuid.UUID(receipt["recap_id"])
    async with setup.factory() as transaction, transaction.begin():
        await service.lock_entitlement(transaction, setup.owner)
        pending = asyncio.create_task(service.read_recap(setup.owner, recap_id))
        await asyncio.sleep(0.05)
        assert not pending.done()
        await transaction.execute(
            update(VoiceRecap).where(VoiceRecap.id == recap_id).values(encrypted_content=None)
        )
    with pytest.raises(HTTPException) as error:
        await asyncio.wait_for(pending, 15)
    assert error.value.status_code == 404


async def test_summary_withdrawal_erases_ciphertext_and_regrant_never_revives_it(
    setup, monkeypatch
):
    from app.api.v1 import consent as api
    from app.voice.recaps import RecapService

    service = RecapService(setup.factory, setup.settings)
    key = uuid.uuid4()
    receipt = await service.create_recap(setup.owner, setup.case_id, key)
    recap_id = uuid.UUID(receipt["recap_id"])
    monkeypatch.setattr(api, "get_settings", lambda: setup.settings)
    monkeypatch.setattr(api, "AsyncSessionLocal", setup.factory)
    before = await finances(setup)
    for action in ("revoke", "grant"):
        result = await api.update_consent(
            api.ConsentRequest(
                user_id=setup.owner,
                scope="voice_summary",
                action=action,
                purpose_version=VOICE_CONSENT_VERSION,
            ),
            setup.owner,
        )
        assert result.status == ("granted" if action == "grant" else "revoked")
    async with setup.factory() as db:
        row = await db.get(VoiceRecap, recap_id)
        assert row.encrypted_content is None and row.request_key == key
    for method in [
        lambda: service.create_recap(setup.owner, setup.case_id, key),
        lambda: service.read_recap(setup.owner, recap_id),
    ]:
        with pytest.raises(HTTPException) as error:
            await method()
        assert error.value.status_code == 404
    assert await finances(setup) == before


async def test_activity_waiting_on_consent_withdrawal_rechecks_before_return(setup):
    await sent(setup)
    async with setup.factory() as transaction, transaction.begin():
        await setup.activity.lock_entitlement(transaction, setup.owner)
        pending = asyncio.create_task(read(setup))
        await asyncio.sleep(0.05)
        assert not pending.done()
        await transaction.execute(
            update(ConsentRecord)
            .where(ConsentRecord.user_id == setup.owner, ConsentRecord.scope == "voice_summary")
            .values(revoked_at=datetime.now(UTC))
        )
    with pytest.raises(HTTPException) as error:
        await asyncio.wait_for(pending, 15)
    assert error.value.status_code == 403
