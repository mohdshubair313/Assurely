"""Advisor review transactions on the isolated policy_review_test_terms database."""

import asyncio
import runpy
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.api.v1 import advisor_reviews as api
from app.api.v1.policy_reviews import review_db
from app.core import advisor_auth
from app.db import advisor_review as store
from app.db.policy_review_store import Reviewer, WorkflowError
from app.graph.nodes.explanation_report import explanation_report_node
from app.models.db.advisor_review import AdvisorDecision
from app.models.db.session import Session
from app.models.db.user import User
from tests.integration.test_policy_publication_workflow import decide as publication_decide
from tests.integration.test_policy_review_workflow import ACTOR, URL
from tests.integration.test_reviewed_policy_terms import (
    compare,
    import_terms,
    request,
    stage_and_publish,
)
from tests.integration.test_reviewed_policy_terms import database as _database
from tests.unit.test_policy_publication import publication_input as _publication_input
from tests.unit.test_policy_review_api import setup as _setup
from tests.unit.test_policy_review_api import token

database = _database
publication_input = _publication_input
pytestmark = pytest.mark.skipif(not URL, reason="Isolated policy-review Postgres required")


async def prepare(factory, publication_input):
    digest, publication_command, command = await stage_and_publish(factory, publication_input)
    await import_terms(factory, digest, command)
    comparison = await compare(factory, digest)
    session_id, owner = uuid.uuid4(), uuid.uuid4()
    state = {
        "session_id": str(session_id),
        "user_id": str(owner),
        "intent": "health",
        "input_status": "accepted",
        "missing_fields": [],
        "reviewed_comparison_request": request(digest).model_dump(mode="json"),
        "draft_output": {"stage": "compare_verify", "reviewed_comparison": comparison},
        "messages": [{"content": "PRIVATE_CHAT"}],
        "user_profile": {"secret": "PRIVATE_PROFILE"},
    }
    state.update(await explanation_report_node(state))
    async with factory() as db, db.begin():
        db.add(User(id=owner, role="customer"))
        await db.flush()
        db.add(Session(id=session_id, user_id=owner, intent="health"))
    return state, digest, publication_command


async def stage(factory, state):
    async with factory() as db, db.begin():
        return await store.stage(db, ACTOR, state["session_id"], state)


def approval():
    return store.DecisionCommand(
        request_key=uuid.uuid4(),
        expected_revision=0,
        action="approve",
        reason="Synthetic advisor review",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


async def decide(factory, digest, command):
    async with factory() as db, db.begin():
        return await store.decide(db, ACTOR, digest, command)


async def test_immutable_binding_approval_revoke_replay_and_namespace(database, publication_input):
    _, factory, _ = database
    state, pub_digest, pub_command = await prepare(factory, publication_input)
    staged = await stage(factory, state)
    digest = staged["report_digest"]
    assert (await stage(factory, state))["report_digest"] == digest
    command = approval()
    first = await decide(factory, digest, command)
    assert first["customer_delivery_authorized"] is False
    async with factory() as db, db.begin():
        read = await store.read(db, ACTOR, digest)
        assert read["review_status"] == "approved" and read["revision"] == 1
        row = (await db.execute(text("SELECT snapshot FROM advisor_reports"))).scalar_one()
        assert "messages" not in row and "user_profile" not in row
    async with factory() as db, db.begin():
        with pytest.raises(WorkflowError, match="not found"):
            await store.read(db, Reviewer(ACTOR.subject, "https://foreign.example/"), digest)
    async with factory() as db, db.begin():
        with pytest.raises(WorkflowError, match="Independent"):
            await store.read(db, Reviewer(uuid.UUID(state["user_id"]), ACTOR.issuer), digest)
    await publication_decide(
        factory,
        pub_digest,
        pub_command.model_copy(
            update={
                "request_key": uuid.uuid4(),
                "expected_revision": 1,
                "action": "revoke",
                "expires_at": None,
            }
        ),
    )
    # Revoke is possible even when policy evidence has become invalid.
    await decide(
        factory,
        digest,
        store.DecisionCommand(
            request_key=uuid.uuid4(),
            expected_revision=1,
            action="revoke",
            reason="Withdraw approval",
        ),
    )
    assert await decide(factory, digest, command) == first  # historical, never current permission
    async with factory() as db, db.begin():
        assert (await store.read(db, ACTOR, digest))["review_status"] == "revoked"
    with pytest.raises(WorkflowError, match="evidence changed"):
        await decide(factory, digest, approval().model_copy(update={"expected_revision": 2}))


async def test_concurrency_changed_key_rollback_and_append_only(database, publication_input):
    _, factory, _ = database
    state, _, _ = await prepare(factory, publication_input)
    digest = (await stage(factory, state))["report_digest"]
    command = approval()
    a, b = await asyncio.wait_for(
        asyncio.gather(
            decide(factory, digest, command),
            decide(factory, digest, command),
        ),
        20,
    )
    assert a == b
    with pytest.raises(WorkflowError, match="different decision"):
        await decide(factory, digest, command.model_copy(update={"reason": "Changed"}))
    with pytest.raises(WorkflowError, match="revision changed"):
        await decide(factory, digest, approval())
    with pytest.raises(RuntimeError, match="rollback"):
        async with factory() as db, db.begin():
            await store.decide(
                db,
                ACTOR,
                digest,
                store.DecisionCommand(
                    request_key=uuid.uuid4(),
                    expected_revision=1,
                    action="revoke",
                    reason="Rollback",
                ),
            )
            raise RuntimeError("rollback")
    async with factory() as db:
        assert len((await db.scalars(select(AdvisorDecision))).all()) == 1
    for statement in (
        "DELETE FROM advisor_reports",
        "UPDATE advisor_decisions SET reason='changed'",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            async with factory() as db, db.begin():
                await db.execute(text(statement))


async def test_expiry_self_review_and_staging_mismatch(database, publication_input, monkeypatch):
    _, factory, _ = database
    state, _, _ = await prepare(factory, publication_input)
    async with factory() as db, db.begin():
        with pytest.raises(WorkflowError, match="Independent"):
            await store.stage(
                db, Reviewer(uuid.UUID(state["user_id"]), ACTOR.issuer), state["session_id"], state
            )
    digest = (await stage(factory, state))["report_digest"]
    with pytest.raises(WorkflowError, match="expiry"):
        await decide(
            factory,
            digest,
            approval().model_copy(
                update={
                    "expires_at": datetime.now(UTC) + timedelta(days=8),
                }
            ),
        )
    await decide(factory, digest, approval())

    class Future(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(UTC) + timedelta(hours=2)

    monkeypatch.setattr(store, "datetime", Future)
    async with factory() as db, db.begin():
        assert (await store.read(db, ACTOR, digest))["review_status"] == "expired"


async def test_signed_http_snapshot_and_decision(database, publication_input, monkeypatch):
    _, factory, _ = database
    state, _, _ = await prepare(factory, publication_input)
    app, _, key, settings = _setup.__wrapped__(monkeypatch)
    settings.auth_issuer = ACTOR.issuer
    settings.advisor_subjects = [str(ACTOR.subject)]
    monkeypatch.setattr(advisor_auth, "get_settings", lambda: settings)
    from unittest.mock import AsyncMock

    from app.api.v1 import message

    monkeypatch.setattr(
        message,
        "_app_graph",
        SimpleNamespace(
            aget_state=AsyncMock(return_value=SimpleNamespace(values=state)),
        ),
    )
    app.include_router(api.router, prefix="/v1")

    async def real_db():
        async with factory() as db, db.begin():
            yield db

    app.dependency_overrides[review_db] = real_db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        headers = token(key, iss=ACTOR.issuer)
        response = await c.post(
            f"/v1/advisor-reviews/sessions/{state['session_id']}/snapshot", headers=headers
        )
        assert response.status_code == 200
        digest = response.json()["report_digest"]
        response = await c.post(
            f"/v1/advisor-reviews/{digest}/decisions",
            headers=headers,
            json=approval().model_dump(mode="json"),
        )
        assert response.status_code == 200 and response.json()["action"] == "approve"
        assert response.json()["customer_delivery_authorized"] is False


async def test_advisor_migration_reverses_only_before_snapshots(database, publication_input):
    engine, factory, _ = database
    migration = runpy.run_path(str(
        Path(__file__).parents[2] / "alembic/versions/007_advisor_review.py"
    ))
    release_migration = runpy.run_path(str(
        Path(__file__).parents[2] / "alembic/versions/008_report_release.py"
    ))

    def run(conn, action):
        with Operations.context(MigrationContext.configure(conn)):
            migration[action]()

    async with engine.begin() as conn:
        def undo_release(connection):
            with Operations.context(MigrationContext.configure(connection)):
                release_migration["downgrade"]()
        await conn.run_sync(undo_release)
        await conn.run_sync(run, "downgrade")
        await conn.run_sync(run, "upgrade")
        def redo_release(connection):
            with Operations.context(MigrationContext.configure(connection)):
                release_migration["upgrade"]()
        await conn.run_sync(redo_release)
    state, _, _ = await prepare(factory, publication_input)
    await stage(factory, state)
    with pytest.raises(DBAPIError, match="Refusing downgrade"):
        async with engine.begin() as conn:
            await conn.run_sync(run, "downgrade")
