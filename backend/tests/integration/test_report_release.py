"""Durable turn invalidation and transaction-time release with synthetic policy data."""

import asyncio
import runpy
import uuid
from pathlib import Path

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.api.v1 import report_release as api
from app.db import report_release as store
from app.db.advisor_review import DecisionCommand
from app.db.policy_review_store import WorkflowError
from app.models.db.report_release import ReleaseReceipt
from tests.integration.test_advisor_review import approval, decide, prepare, stage
from tests.integration.test_policy_review_workflow import ACTOR, URL
from tests.integration.test_reviewed_policy_terms import database as _database
from tests.unit.test_policy_publication import publication_input as _publication_input
from tests.unit.test_policy_review_api import setup as _setup
from tests.unit.test_policy_review_api import token

database = _database
publication_input = _publication_input
pytestmark = pytest.mark.skipif(not URL, reason="Isolated policy-review Postgres required")


async def ready(factory, publication_input, approved=True):
    state, _, _ = await prepare(factory, publication_input)
    owner = uuid.UUID(state["user_id"])
    async with factory() as db, db.begin():
        turn = await store.begin_turn(db, ACTOR.issuer, state["session_id"], owner)
    state["approved"] = approved  # Synthetic guardrail outcome, not production policy approval.
    async with factory() as db, db.begin():
        await store.finish_turn(db, ACTOR.issuer, state["session_id"], turn, state)
    digest = (await stage(factory, state))["report_digest"]
    await decide(factory, digest, approval())
    command = store.ReleaseCommand(request_key=uuid.uuid4(), turn_id=turn, report_digest=digest)
    return state, owner, command


async def release(factory, state, owner, command):
    async with factory() as db, db.begin():
        return await store.release(
            db, ACTOR.issuer, state["session_id"], owner, command, {ACTOR.subject}
        )


async def test_release_retry_restart_and_immutable_receipt(database, publication_input):
    engine, factory, _ = database
    state, owner, command = await ready(factory, publication_input)
    first, second = await asyncio.wait_for(
        asyncio.gather(
            release(factory, state, owner, command),
            release(factory, state, owner, command),
        ),
        20,
    )
    assert first == second and first["output"] == state["output"]
    await engine.dispose()  # Reconnect; no graph checkpoint participates in release.
    assert await release(factory, state, owner, command) == first
    async with factory() as db:
        assert len((await db.scalars(select(ReleaseReceipt))).all()) == 1
    with pytest.raises(DBAPIError, match="append-only"):
        async with factory() as db, db.begin():
            await db.execute(text("DELETE FROM report_release_receipts"))


async def test_new_turn_invalidates_old_report_and_rejected_turn_cannot_restore_it(
    database,
    publication_input,
):
    _, factory, _ = database
    state, owner, command = await ready(factory, publication_input)
    await release(factory, state, owner, command)
    async with factory() as db, db.begin():
        new_turn = await store.begin_turn(db, ACTOR.issuer, state["session_id"], owner)
    with pytest.raises(WorkflowError, match="already running"):
        async with factory() as db, db.begin():
            await store.begin_turn(db, ACTOR.issuer, state["session_id"], owner)
    with pytest.raises(WorkflowError, match="not approved"):
        await release(factory, state, owner, command)
    async with factory() as db, db.begin():
        await store.finish_turn(
            db, ACTOR.issuer, state["session_id"], new_turn, {**state, "input_status": "rejected"}
        )
    async with factory() as db, db.begin():
        row = await store.head(db, ACTOR.issuer, state["session_id"], owner)
        assert row.report_digest is None and not row.guardrail_approved
    with pytest.raises(WorkflowError, match="current turn changed"):
        async with factory() as db, db.begin():
            await store.finish_turn(db, ACTOR.issuer, state["session_id"], command.turn_id, state)


async def test_advisor_cannot_override_guardrail_and_owner_checks(database, publication_input):
    _, factory, _ = database
    state, owner, command = await ready(factory, publication_input, approved=False)
    with pytest.raises(WorkflowError, match="not approved"):
        await release(factory, state, owner, command)
    with pytest.raises(WorkflowError, match="another user"):
        await release(factory, state, uuid.uuid4(), command)
    async with factory() as db:
        assert not (await db.scalars(select(ReleaseReceipt))).all()


async def test_revoked_advisor_and_rollback_block_receipt_replay(database, publication_input):
    _, factory, _ = database
    state, owner, command = await ready(factory, publication_input)
    with pytest.raises(RuntimeError):
        async with factory() as db, db.begin():
            await store.release(
                db, ACTOR.issuer, state["session_id"], owner, command, {ACTOR.subject}
            )
            raise RuntimeError("Synthetic rollback")
    async with factory() as db:
        assert not (await db.scalars(select(ReleaseReceipt))).all()
    await release(factory, state, owner, command)
    await decide(
        factory,
        command.report_digest,
        DecisionCommand(
            request_key=uuid.uuid4(),
            expected_revision=1,
            action="revoke",
            reason="Synthetic revoke",
        ),
    )
    with pytest.raises(WorkflowError, match="advisor approval"):
        await release(factory, state, owner, command)


async def test_owner_signed_http_release_commits_receipt(database, publication_input, monkeypatch):
    _, factory, _ = database
    state, owner, command = await ready(factory, publication_input)
    app, _, key, settings = _setup.__wrapped__(monkeypatch)
    settings.auth_issuer = ACTOR.issuer
    settings.environment = "production"
    settings.advisor_subjects = [str(ACTOR.subject)]
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    monkeypatch.setattr(api, "AsyncSessionLocal", factory)
    app.include_router(api.router, prefix="/v1")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        endpoint = f"/v1/sessions/{state['session_id']}/report-release"
        assert (await c.post(endpoint, json=command.model_dump(mode="json"))).status_code == 401
        response = await c.post(
            endpoint,
            headers=token(key, iss=ACTOR.issuer, sub=str(owner)),
            json=command.model_dump(mode="json"),
        )
        owner_headers = token(key, iss=ACTOR.issuer, sub=str(owner))
        current = await c.get(f"/v1/sessions/{state['session_id']}/report-status",
                              headers=owner_headers)
        assert current.status_code == 200
        assert current.json()["report_digest"] == command.report_digest
        foreign = await c.get(f"/v1/sessions/{state['session_id']}/report-status",
                              headers=token(key, iss=ACTOR.issuer, sub=str(uuid.uuid4())))
        assert foreign.status_code == 403
        settings.environment = "development"
        blocked = await c.post(endpoint, headers=owner_headers,
                                json=command.model_dump(mode="json"))
        assert blocked.status_code == 409
    assert response.status_code == 200 and response.json()["delivery_hold"] is False
    async with factory() as db:
        assert len((await db.scalars(select(ReleaseReceipt))).all()) == 1


async def test_release_migration_refuses_to_destroy_current_turns(database):
    engine, factory, _ = database
    migration = runpy.run_path(str(
        Path(__file__).parents[2] / "alembic/versions/008_report_release.py"
    ))

    def run(conn, action):
        with Operations.context(MigrationContext.configure(conn)):
            migration[action]()

    async with engine.begin() as conn:
        await conn.run_sync(run, "downgrade")
        await conn.run_sync(run, "upgrade")
    async with factory() as db, db.begin():
        await store.begin_turn(db, ACTOR.issuer, "synthetic", uuid.uuid4())
    with pytest.raises(DBAPIError, match="Refusing downgrade"):
        async with engine.begin() as conn:
            await conn.run_sync(run, "downgrade")
