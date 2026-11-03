"""Real Postgres review transactions; requires an explicitly isolated test database."""

import asyncio
import importlib.util
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import policy_review_store as store
from app.db.policy_rule_draft import build_draft
from app.models.db.policy_review import (
    PolicyReviewDraft,
    PolicyReviewEvent,
    PolicyReviewFact,
    PolicySourceBlob,
    PolicyWorkflowReceipt,
)
from tests.unit.test_policy_rule_draft import candidate as _source_candidate

URL = os.environ.get("POLICY_REVIEW_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="Isolated policy-review Postgres URL required")
ACTOR = store.Reviewer(uuid.UUID("00000000-0000-4000-8000-000000000123"), "https://test.example/")


@pytest.fixture
def candidate():
    return _source_candidate.__wrapped__()


@pytest_asyncio.fixture
async def database():
    if not (make_url(URL).database or "").startswith("policy_review_test"):
        raise RuntimeError("Refusing a database without the policy_review_test prefix")
    engine = create_async_engine(URL)
    spec = importlib.util.spec_from_file_location(
        "review_migration",
        Path(__file__).parents[2] / "alembic/versions/004_policy_review_staging.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def migrate(connection, operation):
        with Operations.context(MigrationContext.configure(connection)):
            operation()

    async with engine.begin() as connection:
        await connection.run_sync(migrate, module.upgrade)
    yield engine, async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(migrate, module.downgrade)
    await engine.dispose()


def draft_input(candidate):
    package, sources = candidate
    return build_draft(
        json.dumps(package), sources, as_of=datetime.now(UTC).date()
    ).model_dump_json()


async def stage(factory, candidate, key=None):
    async with factory() as db, db.begin():
        return await store.stage_draft(
            db, ACTOR, key or uuid.uuid4(), draft_input(candidate), candidate[1]
        )


async def review(factory, digest, action, revision, expires=None, key=None):
    command = store.ReviewCommand(
        request_key=key or uuid.uuid4(),
        expected_revision=revision,
        action=action,
        reason="Synthetic integration review",
        expires_at=expires,
    )
    async with factory() as db, db.begin():
        return await store.review_draft(db, ACTOR, digest, command)


async def test_concurrent_staging_and_durable_readback(database, candidate):
    engine, factory = database
    key = uuid.uuid4()
    results = await asyncio.gather(*(stage(factory, candidate, key) for _ in range(5)))
    assert all(result == results[0] for result in results)
    await engine.dispose()  # New connections must reconstruct state entirely from Postgres.
    async with factory() as db, db.begin():
        for model, count in [
            (PolicyReviewDraft, 1),
            (PolicyReviewFact, 10),
            (PolicySourceBlob, 1),
            (PolicyWorkflowReceipt, 1),
        ]:
            assert await db.scalar(select(func.count()).select_from(model)) == count
        saved = await store.read_draft(db, results[0]["draft_digest"])
        assert saved["revision"] == 0 and not saved["production_approved"]


async def test_changed_content_cannot_reuse_key(database, candidate):
    _, factory = database
    key = uuid.uuid4()
    await stage(factory, candidate, key)
    candidate[0]["product"] = "Different synthetic product"
    with pytest.raises(store.WorkflowError, match="different request"):
        await stage(factory, candidate, key)
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(PolicyReviewDraft)) == 1


async def test_atomic_rollback_keeps_no_partial_records(database, candidate):
    _, factory = database
    with pytest.raises(RuntimeError, match="injected failure"):
        async with factory() as db, db.begin():
            await store.stage_draft(db, ACTOR, uuid.uuid4(), draft_input(candidate), candidate[1])
            await db.flush()
            raise RuntimeError("injected failure")
    async with factory() as db:
        for model in [PolicyReviewDraft, PolicyReviewFact, PolicySourceBlob, PolicyWorkflowReceipt]:
            assert await db.scalar(select(func.count()).select_from(model)) == 0


async def test_concurrent_review_revision_and_revocation(database, candidate):
    _, factory = database
    digest = (await stage(factory, candidate))["draft_digest"]
    expiry = datetime.now(UTC) + timedelta(days=1)
    results = await asyncio.gather(
        review(factory, digest, "accept_representation", 0, expiry),
        review(factory, digest, "reject", 0),
        return_exceptions=True,
    )
    assert sum(isinstance(r, dict) for r in results) == 1
    assert sum(isinstance(r, store.WorkflowError) and r.status == 409 for r in results) == 1
    # A fresh acceptance supersedes either first decision; revoke is another immutable event.
    accepted = await review(factory, digest, "accept_representation", 1, expiry)
    async with factory() as db, db.begin():
        before = await store.check_import(db, ACTOR, digest, uuid.uuid4())
        assert before["representation_review"] == "representation_accepted"
        assert before["status"] == "blocked" and not before["approved_for_import"]
    await review(factory, digest, "revoke", 2)
    async with factory() as db, db.begin():
        after = await store.check_import(db, ACTOR, digest, uuid.uuid4())
        assert after["representation_review"] == "revoked" and not after["approved_for_import"]
        assert await db.scalar(select(func.count()).select_from(PolicyReviewEvent)) == 3
        assert accepted["scope"] == "representation_only"


async def test_expiry_and_historical_replay_cannot_release(database, candidate, monkeypatch):
    _, factory = database
    digest = (await stage(factory, candidate))["draft_digest"]
    now = datetime.now(UTC)
    key = uuid.uuid4()
    expires = now + timedelta(days=1)
    original = await review(factory, digest, "accept_representation", 0, expires, key)

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return now + timedelta(days=2)

    monkeypatch.setattr(store, "datetime", Later)
    replay = await review(factory, digest, "accept_representation", 0, expires, key)
    assert replay == original and not replay["approved_for_import"]
    async with factory() as db, db.begin():
        current = await store.check_import(db, ACTOR, digest, uuid.uuid4())
        assert current["representation_review"] == "expired"
        assert not current["production_approved"]


async def test_database_rejects_mutation_of_evidence_and_history(database, candidate):
    _, factory = database
    digest = (await stage(factory, candidate))["draft_digest"]
    await review(factory, digest, "reject", 0)
    for statement in [
        "UPDATE policy_review_drafts SET payload = '{}'::jsonb",
        "DELETE FROM policy_source_blobs",
        "DELETE FROM policy_review_events",
        "UPDATE policy_review_facts SET payload = '{}'::jsonb",
        "DELETE FROM policy_workflow_receipts",
    ]:
        with pytest.raises(DBAPIError, match="append-only"):
            async with factory() as db, db.begin():
                await db.execute(text(statement))


async def test_invalid_source_and_expiry_leave_no_receipt(database, candidate):
    _, factory = database
    raw = draft_input(candidate)
    with pytest.raises(ValueError):
        async with factory() as db, db.begin():
            await store.stage_draft(db, ACTOR, uuid.uuid4(), raw, {"wording": b"%PDF-invalid"})
    digest = (await stage(factory, candidate))["draft_digest"]
    for expiry in [
        datetime.now(UTC) - timedelta(seconds=1),
        datetime.now(UTC) + timedelta(days=91),
    ]:
        with pytest.raises(store.WorkflowError, match="expiry"):
            await review(factory, digest, "accept_representation", 0, expiry)
    with pytest.raises(store.WorkflowError, match="No representation"):
        await review(factory, digest, "revoke", 0)
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(PolicyReviewEvent)) == 0
        assert await db.scalar(select(func.count()).select_from(PolicyWorkflowReceipt)) == 1
