"""Real PostgreSQL request/release transactions using synthetic insurance fixtures."""

import asyncio
import json
import runpy
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.api.v1 import human_review as api
from app.core import security
from app.core.config import Settings
from app.db import advisor_review, auth_identity, human_review_queue
from app.db import human_review as store
from app.db.policy_review_store import WorkflowError
from app.models.db.escalation import Escalation
from app.models.db.human_review import HumanReviewRequest
from app.models.db.report_release import ReleaseReceipt
from app.models.db.session import Session
from app.models.db.user import User
from tests.integration.test_advisor_review import approval, decide
from tests.integration.test_policy_review_workflow import ACTOR, URL
from tests.integration.test_report_release import ready, release
from tests.integration.test_reviewed_policy_terms import database as _database
from tests.unit.test_clerk_auth import bearer, claims
from tests.unit.test_policy_publication import publication_input as _publication_input

database = _database
publication_input = _publication_input
pytestmark = pytest.mark.skipif(not URL, reason="Explicit isolated policy-review database required")


@pytest.fixture
def settings(monkeypatch):
    value = Settings(
        _env_file=None,
        auth_provider="clerk",
        auth_issuer=ACTOR.issuer,
        auth_jwks_url=ACTOR.issuer + ".well-known/jwks.json",
        auth_authorized_parties=["https://assurely.example.test"],
        environment="staging",
        human_review_requests_enabled=True,
        advisor_subjects=[str(ACTOR.subject)],
    )
    monkeypatch.setattr(store, "get_settings", lambda: value)
    monkeypatch.setattr(api, "get_settings", lambda: value)
    return value


async def case(factory, owner=None):
    owner, session = owner or uuid.uuid4(), uuid.uuid4()
    async with factory() as db, db.begin():
        if await db.get(User, owner) is None:
            db.add(User(id=owner, role="customer"))
            await db.flush()
        db.add(Session(id=session, user_id=owner, intent="health"))
    return owner, session


async def request(factory, owner, session, key=None):
    async with factory() as db, db.begin():
        return await store.create(
            db,
            ACTOR.issuer,
            session,
            owner,
            store.RequestCommand(request_key=key or uuid.uuid4()),
        )


async def status(factory, owner, session):
    async with factory() as db, db.begin():
        return await store.read(db, ACTOR.issuer, session, owner)


async def test_concurrent_retry_restart_and_immutable_receipt(database, settings):
    engine, factory, _ = database
    owner, session = await case(factory)
    key = uuid.uuid4()
    values = await asyncio.wait_for(
        asyncio.gather(*(request(factory, owner, session, key) for _ in range(8))),
        20,
    )
    assert all(value == values[0] for value in values)
    receipt = values[0]["request"]
    assert receipt["status"] == "pending"
    assert receipt["delivery_hold"] is True
    assert receipt["human_connected"] is False
    assert receipt["notification_dispatched"] is False
    await engine.dispose()
    assert await request(factory, owner, session, key) == values[0]
    assert (await status(factory, owner, session))["request"] == receipt
    child = """
import asyncio, json, os, sys, uuid
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import Settings
Settings.model_config['env_file'] = None
from app.db import human_review
async def main():
    engine = create_async_engine(os.environ['POLICY_REVIEW_TEST_DATABASE_URL'])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db, db.begin():
        value = await human_review.read(
            db, sys.argv[1], uuid.UUID(sys.argv[3]), uuid.UUID(sys.argv[2])
        )
        print(json.dumps(value, sort_keys=True))
    await engine.dispose()
asyncio.run(main())
"""
    restarted = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-c", child, ACTOR.issuer, str(owner), str(session)],
        capture_output=True,
        text=True,
        check=True,
        timeout=40,
    )
    assert json.loads(restarted.stdout) == values[0]
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(HumanReviewRequest)) == 1
        assert await db.scalar(select(func.count()).select_from(Escalation)) == 1
        # Neither voice quota nor audio-processing consent is a human-review prerequisite.
        assert await db.scalar(text("SELECT count(*) FROM voice_entitlements")) == 0
        assert await db.scalar(text("SELECT count(*) FROM consent_records")) == 0
    for statement in [
        "DELETE FROM human_review_requests",
        "UPDATE human_review_requests SET request_digest=repeat('a',64)",
    ]:
        with pytest.raises(DBAPIError, match="append-only|immutable"):
            async with factory() as db, db.begin():
                await db.execute(text(statement))
    migration = runpy.run_path(
        str(Path(__file__).parents[2] / "alembic/versions/015_human_review_requests.py")
    )

    def downgrade(conn):
        with Operations.context(MigrationContext.configure(conn)):
            migration["downgrade"]()

    with pytest.raises(RuntimeError, match="Retain customer review request history"):
        async with engine.begin() as conn:
            await conn.run_sync(downgrade)


async def test_key_conflict_ownership_and_no_request_enumeration(database, settings):
    _, factory, _ = database
    owner, first = await case(factory)
    _, second = await case(factory, owner)
    stranger, foreign = await case(factory)
    key = uuid.uuid4()
    original = await request(factory, owner, first, key)
    with pytest.raises(WorkflowError) as conflict:
        await request(factory, owner, second, key)
    assert conflict.value.status == 409
    for operation in [request, status]:
        with pytest.raises(WorkflowError) as unauthorized:
            await operation(factory, stranger, first)
        assert unauthorized.value.status in {403, 404}
    assert (await status(factory, owner, second))["request"] is None
    independent = await request(factory, stranger, foreign, key)
    assert independent["request"]["request_id"] != original["request"]["request_id"]


async def test_concurrent_distinct_requests_preserve_assignment_and_enforce_budget(
    database,
    settings,
):
    _, factory, _ = database
    owner, session = await case(factory)
    advisor = uuid.uuid4()
    escalation = uuid.uuid4()
    async with factory() as db, db.begin():
        db.add(User(id=advisor, role="human_advisor"))
        await db.flush()
        db.add(
            Escalation(
                id=escalation,
                session_id=session,
                reason="Synthetic operator reason",
                status="in_review",
                assigned_advisor=advisor,
            )
        )
    keys = [uuid.uuid4() for _ in range(7)]
    outcomes = await asyncio.wait_for(
        asyncio.gather(
            *(request(factory, owner, session, key) for key in keys),
            return_exceptions=True,
        ),
        20,
    )
    accepted = [value for value in outcomes if isinstance(value, dict)]
    denied = [value for value in outcomes if isinstance(value, WorkflowError)]
    assert len(accepted) == 3
    assert len(denied) == 4 and all(value.status == 429 for value in denied)
    assert all(value["request"]["status"] == "in_review" for value in accepted)
    async with factory() as db:
        row = await db.get(Escalation, escalation)
        assert row.assigned_advisor == advisor and row.status == "in_review"
        assert row.reason == "Synthetic operator reason"
        assert await db.scalar(select(func.count()).select_from(Escalation)) == 1
        assert set((await db.scalars(select(HumanReviewRequest.escalation_id))).all()) == {
            escalation
        }
        accepted_key = await db.scalar(select(HumanReviewRequest.request_key).limit(1))
    assert (await request(factory, owner, session, accepted_key))["request"]


async def test_rolled_back_request_does_not_leave_receipt_or_queue(database, settings):
    _, factory, _ = database
    owner, session = await case(factory)
    key = uuid.uuid4()
    with pytest.raises(RuntimeError, match="synthetic"):
        async with factory() as db, db.begin():
            await store.create(
                db, ACTOR.issuer, session, owner, store.RequestCommand(request_key=key)
            )
            raise RuntimeError("synthetic interrupted transaction")
    assert (await status(factory, owner, session))["request"] is None
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(Escalation)) == 0
    assert (await request(factory, owner, session, key))["request"]


async def test_existing_human_assignment_precedes_older_pending_duplicates(database, settings):
    _, factory, _ = database
    owner, session = await case(factory)
    advisor = uuid.uuid4()
    pending, assigned, in_review = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    base = datetime.now(UTC) - timedelta(hours=3)
    records = [
        (pending, "pending", None, "Earlier pending reason", base),
        (assigned, "assigned", advisor, "Assigned private reason", base + timedelta(hours=1)),
        (in_review, "in_review", advisor, "Review private reason", base + timedelta(hours=2)),
    ]

    def escalation(record):
        identifier, state, human, reason, created = record
        return Escalation(
            id=identifier,
            session_id=session,
            status=state,
            assigned_advisor=human,
            reason=reason,
            created_at=created,
        )

    async with factory() as db, db.begin():
        db.add(User(id=advisor, role="advisor"))
        await db.flush()
        db.add_all([escalation(record) for record in records[:2]])
    first = await request(factory, owner, session)
    assert first["request"]["status"] == "assigned"
    async with factory() as db, db.begin():
        initial = await db.get(HumanReviewRequest, uuid.UUID(first["request"]["request_id"]))
        assert initial.escalation_id == assigned
        db.add(escalation(records[2]))
    second = await request(factory, owner, session)
    assert second["request"]["status"] == "in_review"
    async with factory() as db:
        latest = await db.get(HumanReviewRequest, uuid.UUID(second["request"]["request_id"]))
        assert latest.escalation_id == in_review
        # Selecting a canonical row must not rewrite duplicate assignments or private notes.
        actual = (
            await db.execute(
                select(
                    Escalation.id,
                    Escalation.status,
                    Escalation.assigned_advisor,
                    Escalation.reason,
                    Escalation.created_at,
                ).where(Escalation.session_id == session)
            )
        ).all()
        assert {tuple(row) for row in actual} == set(records)


@pytest.mark.parametrize(
    "change",
    [
        {"human_review_requests_enabled": False},
        {"environment": "development"},
        {"auth_provider": "legacy_oidc"},
    ],
)
async def test_creation_gates_fail_closed_without_queue_mutation(database, settings, change):
    _, factory, _ = database
    owner, session = await case(factory)
    for field, value in change.items():
        setattr(settings, field, value)
    with pytest.raises(WorkflowError) as blocked:
        await request(factory, owner, session)
    assert blocked.value.status in {409, 503}
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(HumanReviewRequest)) == 0


async def test_new_request_blocks_old_approval_and_release_receipt_until_fresh_human_decision(
    database,
    settings,
    publication_input,
    monkeypatch,
):
    _, factory, _ = database
    state, owner, command = await ready(factory, publication_input)
    original = await release(factory, state, owner, command)
    session = uuid.UUID(state["session_id"])
    created = await request(factory, owner, session)
    assert created["request"]["delivery_hold"] is True
    settings.human_review_requests_enabled = False
    with pytest.raises(WorkflowError) as held:
        await release(factory, state, owner, command)
    assert held.value.status == 409
    # Rolling back a creation flag cannot erase the durable hold or fabricate approval.
    assert (await status(factory, owner, session))["request"]["status"] != "decision_recorded"
    async with factory() as db, db.begin():
        db.add(User(id=ACTOR.subject, role="advisor"))
        await db.flush()
        assignment = await db.scalar(select(Escalation).where(Escalation.session_id == session))
        assignment.assigned_advisor = ACTOR.subject
        assignment.status = "assigned"
    monkeypatch.setattr(advisor_review, "get_settings", lambda: settings)
    fresh = approval().model_copy(update={"expected_revision": 1})
    await decide(factory, command.report_digest, fresh)
    assert (await status(factory, owner, session))["request"]["status"] == "decision_recorded"
    fresh_release = command.model_copy(update={"request_key": uuid.uuid4()})
    delivered = await release(factory, state, owner, fresh_release)
    assert delivered["delivery_hold"] is False
    assert delivered["output"] == original["output"]
    assert (
        delivered["release_receipt"]["advisor_event_id"]
        != (original["release_receipt"]["advisor_event_id"])
    )
    # Historical success still cannot be replayed as authority for a later decision.
    with pytest.raises(WorkflowError):
        await release(factory, state, owner, command)
    await decide(
        factory,
        command.report_digest,
        advisor_review.DecisionCommand(
            request_key=uuid.uuid4(),
            expected_revision=2,
            action="revoke",
            reason="Synthetic revoke",
        ),
    )
    with pytest.raises(WorkflowError):
        await release(factory, state, owner, fresh_release)
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(ReleaseReceipt)) == 2


async def test_enforcement_uses_strict_db_time_and_never_releases_on_flag_rollback(
    database,
    settings,
):
    _, factory, _ = database
    owner, session = await case(factory)
    await request(factory, owner, session)
    async with factory() as db:
        at = await db.scalar(select(HumanReviewRequest.requested_at))
    settings.human_review_requests_enabled = False
    async with factory() as db, db.begin():
        await store.enforce_fresh_decision(
            db,
            ACTOR.issuer,
            session,
            owner,
            at + timedelta(microseconds=1),
        )
    with pytest.raises(WorkflowError):
        async with factory() as db, db.begin():
            await store.enforce_fresh_decision(
                db,
                ACTOR.issuer,
                session,
                owner,
                at - timedelta(microseconds=1),
            )
    with pytest.raises(WorkflowError):
        async with factory() as db, db.begin():
            await store.enforce_fresh_decision(db, ACTOR.issuer, session, owner, at)


async def test_uncommitted_request_serializes_old_release_on_separate_transaction(
    database,
    settings,
    publication_input,
):
    _, factory, _ = database
    state, owner, command = await ready(factory, publication_input)
    async with factory() as db, db.begin():
        await store.create(
            db,
            ACTOR.issuer,
            uuid.UUID(state["session_id"]),
            owner,
            store.RequestCommand(request_key=uuid.uuid4()),
        )
        pending = asyncio.create_task(release(factory, state, owner, command))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(pending), 0.15)
    # After the first transaction commits, the waiting release must see its hold.
    with pytest.raises(WorkflowError) as held:
        await asyncio.wait_for(pending, 10)
    assert held.value.status == 409
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(ReleaseReceipt)) == 0


async def test_missing_table_preserves_old_release_only_when_feature_disabled(database, settings):
    engine, factory, _ = database
    migration = runpy.run_path(
        str(Path(__file__).parents[2] / "alembic/versions/015_human_review_requests.py")
    )

    def downgrade(conn):
        with Operations.context(MigrationContext.configure(conn)):
            migration["downgrade"]()

    async with engine.begin() as conn:
        await conn.run_sync(downgrade)
    owner, session = await case(factory)
    with pytest.raises(WorkflowError) as missing:
        async with factory() as db, db.begin():
            await store.enforce_fresh_decision(db, ACTOR.issuer, session, owner, datetime.now(UTC))
    assert missing.value.status == 503
    settings.human_review_requests_enabled = False
    async with factory() as db, db.begin():
        await store.enforce_fresh_decision(db, ACTOR.issuer, session, owner, datetime.now(UTC))


async def test_owner_budget_is_serialized_across_cases_and_retry_survives_limit(database, settings):
    _, factory, _ = database
    owner = uuid.uuid4()
    cases = [(await case(factory, owner))[1] for _ in range(21)]
    first_key = uuid.uuid4()
    first = await request(factory, owner, cases[0], first_key)
    for session in cases[1:20]:
        await request(factory, owner, session)
    with pytest.raises(WorkflowError) as limited:
        await request(factory, owner, cases[20])
    assert limited.value.status == 429
    assert await request(factory, owner, cases[0], first_key) == first
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(HumanReviewRequest)) == 20


async def test_operator_queue_is_minimized_namespaced_latest_and_bounded(database, settings):
    _, factory, _ = database
    owner, first = await case(factory)
    _, second = await case(factory, owner)
    await request(factory, owner, first)
    latest = await request(factory, owner, first)
    await request(factory, owner, second)
    async with factory() as db, db.begin():
        queue = await human_review_queue.read_queue(db, ACTOR.issuer, limit=1)
    assert len(queue["items"]) == 1 and queue["truncated"] is True
    assert queue["notification_confirmed"] is False and queue["delivery_authorized"] is False
    async with factory() as db, db.begin():
        full = await human_review_queue.read_queue(db, ACTOR.issuer)
        foreign = await human_review_queue.read_queue(db, "https://foreign.example.test/")
    assert foreign["items"] == []
    assert len(full["items"]) == 2
    first_entry = next(value for value in full["items"] if value["session_id"] == first)
    assert str(first_entry["request_id"]) == latest["request"]["request_id"]
    assert set(first_entry) == {
        "request_id",
        "escalation_id",
        "session_id",
        "requested_at",
        "status",
    }
    async with factory() as db, db.begin():
        row = await db.scalar(select(Escalation).where(Escalation.session_id == first))
        row.status = "resolved"
    async with factory() as db, db.begin():
        assert len((await human_review_queue.read_queue(db, ACTOR.issuer))["items"]) == 1
    # Defense in depth: a subsequent ownership change cannot expose stale requests.
    async with factory() as db, db.begin():
        new_owner = uuid.uuid4()
        db.add(User(id=new_owner, role="customer"))
        await db.flush()
        (await db.get(Session, second)).user_id = new_owner
    async with factory() as db, db.begin():
        assert (await human_review_queue.read_queue(db, ACTOR.issuer))["items"] == []


async def test_signed_clerk_http_ownership_read_and_committed_request(
    database, settings, monkeypatch
):
    _, factory, _ = database
    owner, session = await case(factory)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    from types import SimpleNamespace

    monkeypatch.setattr(api, "AsyncSessionLocal", factory)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    monkeypatch.setattr(
        security,
        "_jwks_client",
        lambda _: SimpleNamespace(
            get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key()),
        ),
    )
    foreign = uuid.uuid4()
    monkeypatch.setattr(
        auth_identity,
        "resolve_identity",
        lambda _, subject: owner if subject == "user_synthetic123" else foreign,
    )
    app = FastAPI()
    app.include_router(api.router, prefix="/v1")
    endpoint = f"/v1/sessions/{session}/human-review"

    def headers(subject="user_synthetic123"):
        return {
            "Authorization": "Bearer "
            + bearer(
                key,
                claims(iss=ACTOR.issuer, sub=subject, azp="https://assurely.example.test"),
            ).credentials
        }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        assert (await client.get(endpoint)).status_code == 401
        empty = await client.get(endpoint, headers=headers())
        assert empty.status_code == 200 and empty.json()["request"] is None
        body = {"request_key": str(uuid.uuid4())}
        created = await client.post(endpoint, headers=headers(), json=body)
        assert created.status_code == 200
        assert (await client.post(endpoint, headers=headers(), json=body)).json() == created.json()
        assert (await client.get(endpoint, headers=headers("user_foreign123"))).status_code in {
            403,
            404,
        }
        assert (
            await client.post(
                endpoint,
                headers=headers(),
                json={
                    **body,
                    "assigned_advisor": str(owner),
                },
            )
        ).status_code == 422
    persisted = await status(factory, owner, session)
    assert persisted == created.json()
    assert "assigned_advisor" not in persisted["request"]
    assert "report_digest" not in persisted["request"]
