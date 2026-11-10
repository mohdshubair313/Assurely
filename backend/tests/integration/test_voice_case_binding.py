"""Actual PostgreSQL release/binding checks with synthetic, non-network media."""

import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError

from app.core.config import Settings
from app.core.consent import CONSENT_VERSION, VOICE_CONSENT_VERSION
from app.db import advisor_review, human_review, policy_publication_store, report_release
from app.db.policy_review_store import WorkflowError
from app.models.db.auth_identity import AuthIdentity
from app.models.db.consent_record import ConsentRecord
from app.models.db.escalation import Escalation
from app.models.db.policy_publication import PolicyPublicationEvent
from app.models.db.report_release import ReleaseReceipt
from app.models.db.session import Session
from app.models.db.user import User
from app.models.db.voice import VoiceEntitlement, VoiceSession, VoiceUsageLedger
from app.models.db.voice_lifecycle import VoiceManagedOperation
from app.voice.managed import ManagedVoiceService
from tests.integration.test_advisor_review import decide
from tests.integration.test_policy_publication_workflow import decide as publication_decide
from tests.integration.test_policy_review_workflow import ACTOR, URL
from tests.integration.test_report_release import ready
from tests.integration.test_reviewed_policy_terms import database as _database
from tests.integration.test_voice_next import Provider
from tests.unit.test_policy_publication import publication_input as _publication_input

database = _database
publication_input = _publication_input
pytestmark = pytest.mark.skipif(not URL, reason="Dedicated disposable policy database required")


@pytest_asyncio.fixture
async def setup(database, publication_input, monkeypatch):
    from app.voice.case_binding import VoiceCaseBindingService

    engine, factory, _ = database
    # All approvals and policy facts here are synthetic transaction fixtures.
    state, owner, command = await ready(factory, publication_input)
    agent = uuid.uuid4()
    settings = Settings(
        _env_file=None,
        environment="staging",
        auth_provider="clerk",
        auth_issuer=ACTOR.issuer,
        auth_jwks_url=ACTOR.issuer.rstrip("/") + "/.well-known/jwks.json",
        auth_authorized_parties=["https://assurely.synthetic.test"],
        advisor_subjects=[str(ACTOR.subject)],
        human_review_requests_enabled=True,
        voice_case_binding_enabled=True,
        voice_tools_enabled=True,
        voice_development_enabled=True,
        vaani_dispatch_enabled=True,
        vaani_byol_enabled=True,
        vaani_ingress_enabled=True,
        vaani_dev_agent_reviewed=True,
        vaani_agent_id=str(agent),
        vaani_api_key="synthetic-only-provider-key",
        vaani_byol_token="synthetic-only-byol-" + "b" * 40,
        vaani_staging_base_url="https://synthetic.trycloudflare.com",
        vaani_webhook_secret="synthetic-only-webhook-" + "w" * 40,
        voice_test_subjects=[str(owner)],
        voice_token_encryption_key=Fernet.generate_key().decode(),
        voice_max_call_seconds=300,
    )
    async with factory() as db, db.begin():
        db.add(
            AuthIdentity(
                id=uuid.uuid4(),
                provider="clerk",
                issuer=settings.auth_issuer,
                subject="user_Synthetic" + owner.hex,
                user_id=owner,
                disabled=False,
            )
        )
        if await db.get(User, ACTOR.subject) is None:
            db.add(User(id=ACTOR.subject, role="human_advisor"))
            await db.flush()
        db.add(
            Escalation(
                id=uuid.uuid4(),
                session_id=uuid.UUID(state["session_id"]),
                reason="Synthetic independent human assignment",
                status="assigned",
                assigned_advisor=ACTOR.subject,
            )
        )
        for scope in ["process_comparison", "voice_microphone", "voice_vendor_processing"]:
            db.add(
                ConsentRecord(
                    user_id=owner,
                    scope=scope,
                    purpose_version=CONSENT_VERSION
                    if scope == "process_comparison"
                    else VOICE_CONSENT_VERSION,
                )
            )
    monkeypatch.setattr(advisor_review, "get_settings", lambda: settings)
    monkeypatch.setattr(human_review, "get_settings", lambda: settings)
    provider = Provider(agent)
    managed = ManagedVoiceService(factory, settings, provider)
    voice, _ = await managed.reserve(owner, uuid.uuid4())
    await managed.advance(owner, voice.id)
    await managed.advance(owner, voice.id)
    await managed.advance(owner, voice.id, connect=True)
    assert (await managed.view(owner, voice.id))["allowed"]
    service = VoiceCaseBindingService(factory, settings, provider)
    return SimpleNamespace(
        engine=engine,
        factory=factory,
        settings=settings,
        provider=provider,
        managed=managed,
        service=service,
        voice=voice,
        owner=owner,
        state=state,
        command=command,
        case_id=uuid.UUID(state["session_id"]),
    )


async def bind(setup, key=None, case_id=None, voice_id=None, owner=None):
    return await setup.service.bind(
        owner or setup.owner,
        voice_id or setup.voice.id,
        case_id or setup.case_id,
        key or uuid.uuid4(),
    )


async def captions(setup):
    return await setup.service.captions(setup.owner, setup.voice.id)


async def assert_held(setup):
    with pytest.raises((HTTPException, WorkflowError)) as error:
        await captions(setup)
    assert getattr(error.value, "status_code", getattr(error.value, "status", None)) in {
        403,
        404,
        409,
        503,
    }


async def test_concurrent_retry_exact_release_binding_and_restart(setup):
    from app.models.db.voice_case_binding import VoiceCaseBinding
    from app.voice.case_binding import VoiceCaseBindingService

    key = uuid.uuid4()
    values = await asyncio.wait_for(
        asyncio.gather(*(bind(setup, key) for _ in range(6))),
        25,
    )
    assert sum(created for _, created in values) == 1
    assert all(value == values[0][0] for value, _ in values)
    async with setup.factory() as db:
        assert await db.scalar(select(func.count()).select_from(VoiceCaseBinding)) == 1
        assert await db.scalar(select(func.count()).select_from(ReleaseReceipt)) == 1
        row = await db.scalar(
            select(VoiceCaseBinding).where(
                VoiceCaseBinding.voice_session_id == setup.voice.id,
            )
        )
        assert row.owner_id == setup.owner and row.issuer == ACTOR.issuer
        assert row.case_id == setup.case_id and row.turn_id == setup.command.turn_id
        assert row.report_digest == setup.command.report_digest
        receipt = await db.get(ReleaseReceipt, row.release_receipt_id)
        assert row.advisor_event_id == receipt.advisor_event_id
        assert receipt.owner_id == setup.owner and receipt.session_id == setup.case_id
    packet = await captions(setup)
    assert [sentence["text"] for sentence in packet["sentences"]] == [
        sentence["text"] for sentence in setup.state["output"]["sentences"]
    ]
    assert "PRIVATE_CHAT" not in str(packet) and "PRIVATE_PROFILE" not in str(packet)
    await setup.engine.dispose()
    setup.service = VoiceCaseBindingService(setup.factory, setup.settings, setup.provider)
    retried, created = await bind(setup, key)
    assert retried == values[0][0] and created is False
    refreshed = await captions(setup)
    assert refreshed["sentences"] == packet["sentences"]
    assert refreshed["case_id"] == packet["case_id"]
    assert refreshed["realtime_transcript"] is False
    assert refreshed["external_speech_enabled"] is False
    assert (
        0
        < (datetime.fromisoformat(refreshed["expires_at"]) - datetime.now(UTC)).total_seconds()
        <= 10
    )
    assert setup.provider.created == setup.provider.connected == 1


async def test_binding_is_append_only_and_populated_downgrade_refuses_loss(setup):
    import runpy
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    await bind(setup)
    for statement in [
        "DELETE FROM voice_case_bindings",
        "UPDATE voice_case_bindings SET request_key=gen_random_uuid()",
    ]:
        with pytest.raises(DBAPIError):
            async with setup.factory() as db, db.begin():
                await db.execute(text(statement))
    migration = next((Path(__file__).parents[2] / "alembic/versions").glob("016_*.py"))
    module = runpy.run_path(str(migration))

    def downgrade(connection):
        with Operations.context(MigrationContext.configure(connection)):
            module["downgrade"]()

    with pytest.raises(RuntimeError, match="Retain voice binding history"):
        async with setup.engine.begin() as connection:
            await connection.run_sync(downgrade)


async def test_new_python_process_recovers_binding_from_database_without_dispatch(setup):
    bound, _ = await bind(setup)
    script = """
import asyncio, json, sys, uuid
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import Settings
Settings.model_config['env_file'] = None
from app.db import advisor_review
from app.voice.case_binding import VoiceCaseBindingService
async def main():
    url, voice, owner, advisor, issuer = sys.argv[1:]
    owner, voice = uuid.UUID(owner), uuid.UUID(voice)
    cfg = Settings(_env_file=None, environment='staging', auth_provider='clerk',
      auth_issuer=issuer, advisor_subjects=[advisor], voice_test_subjects=[str(owner)],
      voice_case_binding_enabled=True, voice_tools_enabled=True,
      voice_development_enabled=True, vaani_byol_enabled=True, vaani_dev_agent_reviewed=True)
    advisor_review.get_settings = lambda: cfg
    engine = create_async_engine(url)
    try:
        result = await VoiceCaseBindingService(
          async_sessionmaker(engine, expire_on_commit=False), cfg).captions(owner, voice)
        print(json.dumps({'binding_id': result['binding_id'],
          'count': len(result['sentences']), 'realtime_transcript': result['realtime_transcript'],
          'external_speech_enabled': result['external_speech_enabled']}))
    finally:
        await engine.dispose()
asyncio.run(main())
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        script,
        URL,
        str(setup.voice.id),
        str(setup.owner),
        str(ACTOR.subject),
        ACTOR.issuer,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), 25)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    assert process.returncode == 0
    child = json.loads(stdout)
    assert child == {
        "binding_id": bound["binding_id"],
        "count": len(setup.state["output"]["sentences"]),
        "realtime_transcript": False,
        "external_speech_enabled": False,
    }
    assert setup.provider.created == setup.provider.connected == 1


async def test_key_conflict_and_no_case_rebinding(setup):
    key = uuid.uuid4()
    await bind(setup, key)
    second = uuid.uuid4()
    async with setup.factory() as db, db.begin():
        db.add(Session(id=second, user_id=setup.owner, intent="health"))
    for changed_key, changed_case in [(uuid.uuid4(), setup.case_id), (key, second)]:
        with pytest.raises((HTTPException, WorkflowError)) as error:
            await bind(setup, changed_key, changed_case)
        assert getattr(error.value, "status_code", getattr(error.value, "status", None)) == 409


async def test_concurrent_distinct_keys_cannot_rebind_same_voice(setup):
    from app.models.db.voice_case_binding import VoiceCaseBinding

    values = await asyncio.wait_for(
        asyncio.gather(
            *(bind(setup, uuid.uuid4()) for _ in range(4)),
            return_exceptions=True,
        ),
        20,
    )
    assert sum(isinstance(value, tuple) for value in values) == 1
    denied = [value for value in values if isinstance(value, HTTPException)]
    assert len(denied) == 3 and all(error.status_code == 409 for error in denied)
    async with setup.factory() as db:
        assert await db.scalar(select(func.count()).select_from(VoiceCaseBinding)) == 1
        assert await db.scalar(select(func.count()).select_from(ReleaseReceipt)) == 1


async def test_same_key_conflict_across_two_owned_voice_sessions(setup):
    key = uuid.uuid4()
    await bind(setup, key)
    async with setup.factory() as db, db.begin():
        await db.execute(
            update(VoiceEntitlement)
            .where(
                VoiceEntitlement.user_id == setup.owner,
            )
            .values(concurrency_limit=2)
        )
    second, _ = await setup.managed.reserve(setup.owner, uuid.uuid4())
    for _ in range(2):
        await setup.managed.advance(setup.owner, second.id)
    await setup.managed.advance(setup.owner, second.id, connect=True)
    with pytest.raises(HTTPException) as error:
        await bind(setup, key, voice_id=second.id)
    assert error.value.status_code == 409


async def test_initial_missing_consent_rolls_back_binding_and_release(setup):
    from app.models.db.voice_case_binding import VoiceCaseBinding

    async with setup.factory() as db, db.begin():
        row = await db.scalar(
            select(ConsentRecord).where(
                ConsentRecord.user_id == setup.owner,
                ConsentRecord.scope == "process_comparison",
            )
        )
        row.revoked_at = datetime.now(UTC)
    with pytest.raises(HTTPException) as error:
        await bind(setup)
    assert error.value.status_code == 403
    async with setup.factory() as db:
        assert await db.scalar(select(func.count()).select_from(VoiceCaseBinding)) == 0
        assert await db.scalar(select(func.count()).select_from(ReleaseReceipt)) == 0


async def test_own_voice_cannot_bind_foreign_owned_case(setup):
    foreign, case = uuid.uuid4(), uuid.uuid4()
    async with setup.factory() as db, db.begin():
        db.add(User(id=foreign, role="customer"))
        await db.flush()
        db.add(Session(id=case, user_id=foreign, intent="health"))
    with pytest.raises(HTTPException) as error:
        await bind(setup, case_id=case)
    assert error.value.status_code in {403, 404}


async def test_cross_user_and_issuer_cannot_read_or_bind(setup):
    await bind(setup)
    with pytest.raises((HTTPException, WorkflowError)):
        await bind(setup, owner=uuid.uuid4())
    with pytest.raises((HTTPException, WorkflowError)):
        await setup.service.captions(uuid.uuid4(), setup.voice.id)
    setup.settings.auth_issuer = "https://foreign.synthetic.test"
    await assert_held(setup)


@pytest.mark.parametrize(
    "scope", ["process_comparison", "voice_microphone", "voice_vendor_processing"]
)
@pytest.mark.parametrize("mode", ["missing", "revoked"])
async def test_missing_or_revoked_consent_blocks_bound_text(setup, scope, mode):
    await bind(setup)
    async with setup.factory() as db, db.begin():
        row = await db.scalar(
            select(ConsentRecord).where(
                ConsentRecord.user_id == setup.owner,
                ConsentRecord.scope == scope,
            )
        )
        if mode == "missing":
            await db.delete(row)
        else:
            row.revoked_at = datetime.now(UTC)
    await assert_held(setup)


@pytest.mark.parametrize(
    "change", ["expired", "end_requested", "call_terminating", "disabled_identity"]
)
async def test_voice_authorization_changes_do_not_release_reservation(setup, change):
    from app.models.db.voice_provider import VoiceProviderCall

    await bind(setup)
    async with setup.factory() as db, db.begin():
        if change == "expired":
            row = await db.get(VoiceSession, setup.voice.id)
            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        elif change == "end_requested":
            row = await db.get(VoiceManagedOperation, setup.voice.id)
            row.end_requested = True
        elif change == "call_terminating":
            row = await db.get(VoiceProviderCall, setup.voice.id)
            row.phase = "termination_required"
        else:
            await db.execute(
                update(AuthIdentity)
                .where(
                    AuthIdentity.user_id == setup.owner,
                )
                .values(disabled=True)
            )
    await assert_held(setup)
    async with setup.factory() as db:
        entitlement = await db.scalar(
            select(VoiceEntitlement).where(
                VoiceEntitlement.user_id == setup.owner,
            )
        )
        assert entitlement.reserved_seconds == setup.voice.reserved_seconds
        assert entitlement.consumed_seconds == 0
        assert await db.scalar(select(func.count()).select_from(VoiceUsageLedger)) == 1


async def test_new_human_request_invalidates_bound_release_even_after_flag_rollback(setup):
    await bind(setup)
    async with setup.factory() as db, db.begin():
        await human_review.create(
            db,
            ACTOR.issuer,
            setup.case_id,
            setup.owner,
            human_review.RequestCommand(request_key=uuid.uuid4()),
        )
    setup.settings.human_review_requests_enabled = False
    await assert_held(setup)


async def test_revoked_advisor_approval_blocks_caption_replay(setup):
    await bind(setup)
    await decide(
        setup.factory,
        setup.command.report_digest,
        advisor_review.DecisionCommand(
            request_key=uuid.uuid4(),
            expected_revision=1,
            action="revoke",
            reason="Synthetic independent approval withdrawal",
        ),
    )
    await assert_held(setup)


async def test_current_advisor_expiry_blocks_bound_caption_replay(setup):
    await decide(
        setup.factory,
        setup.command.report_digest,
        advisor_review.DecisionCommand(
            request_key=uuid.uuid4(),
            expected_revision=1,
            action="approve",
            reason="Synthetic short-lived review expiry probe",
            expires_at=datetime.now(UTC) + timedelta(seconds=2),
        ),
    )
    await bind(setup)
    await asyncio.sleep(2.1)
    await assert_held(setup)


async def test_new_human_request_and_bind_race_remains_held(setup):
    async def request_review():
        async with setup.factory() as db, db.begin():
            return await human_review.create(
                db,
                ACTOR.issuer,
                setup.case_id,
                setup.owner,
                human_review.RequestCommand(request_key=uuid.uuid4()),
            )

    values = await asyncio.wait_for(
        asyncio.gather(
            bind(setup),
            request_review(),
            return_exceptions=True,
        ),
        20,
    )
    assert isinstance(values[1], dict)
    if isinstance(values[0], BaseException):
        assert isinstance(values[0], HTTPException) and values[0].status_code == 409
    await assert_held(setup)


async def test_new_report_turn_does_not_rebind_active_voice(setup):
    await bind(setup)
    async with setup.factory() as db, db.begin():
        await report_release.begin_turn(db, ACTOR.issuer, str(setup.case_id), setup.owner)
    await assert_held(setup)


async def test_revoked_policy_publication_blocks_captions(setup):
    await bind(setup)
    async with setup.factory() as db:
        event = await db.scalar(
            select(PolicyPublicationEvent).where(
                PolicyPublicationEvent.action == "publish",
            )
        )
    await publication_decide(
        setup.factory,
        event.publication_digest,
        policy_publication_store.PublishCommand(
            request_key=uuid.uuid4(),
            expected_revision=event.revision,
            representation_event_id=event.representation_event_id,
            action="revoke",
            reason="Synthetic source publication withdrawn",
        ),
    )
    await assert_held(setup)


async def test_feature_rollback_and_unbound_session_are_closed(setup):
    await assert_held(setup)
    await bind(setup)
    setup.settings.voice_case_binding_enabled = False
    await assert_held(setup)
