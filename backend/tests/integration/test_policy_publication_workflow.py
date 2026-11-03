"""Real PostgreSQL publication transactions, serialization and runtime fail-closed checks."""

import asyncio
import importlib.util
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.db import policy_publication_store as store
from app.db import policy_review_store as review
from app.db.policy_publication_contract import FactScope, Predicate
from app.db.policy_rule_draft import assess_draft, build_draft
from app.models.db.policy_publication import PolicyPublication, PolicyPublicationEvent
from tests.integration.test_policy_review_workflow import ACTOR, URL
from tests.integration.test_policy_review_workflow import database as _review_database
from tests.unit.test_policy_publication import context
from tests.unit.test_policy_publication import publication_input as _publication_input

review_database = _review_database
publication_input = _publication_input

pytestmark = pytest.mark.skipif(not URL, reason="Isolated policy-review Postgres URL required")
PUBLISHER = review.Reviewer(uuid.UUID("00000000-0000-4000-8000-000000000456"), ACTOR.issuer)


@pytest_asyncio.fixture
async def database(review_database):
    engine, factory = review_database
    spec = importlib.util.spec_from_file_location(
        "publication_migration",
        Path(__file__).parents[2] / "alembic/versions/005_policy_publication.py",
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def migrate(connection, operation):
        with Operations.context(MigrationContext.configure(connection)):
            operation()

    async with engine.begin() as connection:
        await connection.run_sync(migrate, migration.upgrade)
    yield engine, factory
    async with engine.begin() as connection:
        await connection.run_sync(migrate, migration.downgrade)


async def prepare(factory, publication_input):
    draft, sources, manifest = publication_input
    async with factory() as db, db.begin():
        staged = await review.stage_draft(db, ACTOR, uuid.uuid4(), draft.model_dump_json(), sources)
    assert staged["draft_digest"] == manifest.draft_digest
    async with factory() as db, db.begin():
        representation = await review.review_draft(
            db,
            ACTOR,
            manifest.draft_digest,
            review.ReviewCommand(
                request_key=uuid.uuid4(),
                expected_revision=0,
                action="accept_representation",
                reason="Synthetic representation review",
                expires_at=datetime.now(UTC) + timedelta(days=2),
            ),
        )
    async with factory() as db, db.begin():
        proposal = await store.propose(
            db,
            ACTOR,
            store.ProposeCommand(
                request_key=uuid.uuid4(),
                manifest=manifest,
            ),
        )
    command = store.PublishCommand(
        request_key=uuid.uuid4(),
        expected_revision=0,
        action="publish",
        representation_event_id=uuid.UUID(representation["event_id"]),
        reason="Independent synthetic capability and source review",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    return proposal["publication_digest"], command


async def decide(factory, digest, command, actor=PUBLISHER):
    async with factory() as db, db.begin():
        return await store.decide(db, actor, digest, command)


async def lookup(factory, digest, **changes):
    async with factory() as db, db.begin():
        return await store.lookup(
            db,
            issuer=ACTOR.issuer,
            digest=digest,
            capability="coverage_options",
            context=context(**changes),
        )


async def test_publication_persists_exact_discrete_facts_and_real_verification(
    database, publication_input
):
    engine, factory = database
    digest, command = await prepare(factory, publication_input)
    assert (await lookup(factory, digest))["reason"] == "pending"
    receipt = await decide(factory, digest, command)
    await engine.dispose()
    result = await lookup(factory, digest)
    assert result["status"] == "available"
    assert result["facts"][0]["value"]["amounts"] == [50_000_000, 100_000_000]
    assert result["facts"][0]["value"]["unit"] == "paise"
    assert result["facts"][0]["last_verified"] == receipt["recorded_at"][:10]
    assert result["facts"][0]["source"][0]["sha256"]
    assert (await lookup(factory, digest, transaction="renewal"))["status"] == "unavailable"
    async with factory() as db, db.begin():
        other = await store.lookup(
            db, issuer=ACTOR.issuer, digest=digest, capability="base_ped_wait", context=context()
        )
        assert other["reason"] == "capability_not_published" and other["facts"] == []


async def test_self_publication_and_stale_review_are_rejected(database, publication_input):
    _, factory = database
    digest, command = await prepare(factory, publication_input)
    with pytest.raises(review.WorkflowError, match="different authorized"):
        await decide(factory, digest, command, actor=ACTOR)
    command.representation_event_id = uuid.uuid4()
    with pytest.raises(review.WorkflowError, match="exact representation"):
        await decide(factory, digest, command)
    assert (await lookup(factory, digest))["reason"] == "pending"


async def test_concurrent_duplicate_publish_is_idempotent_and_changed_key_fails(
    database, publication_input
):
    _, factory = database
    digest, command = await prepare(factory, publication_input)
    results = await asyncio.gather(*(decide(factory, digest, command) for _ in range(5)))
    assert all(result == results[0] for result in results)
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(PolicyPublicationEvent)) == 1
    command.reason = "Different decision body"
    with pytest.raises(review.WorkflowError, match="different request"):
        await decide(factory, digest, command)


async def test_concurrent_overlapping_proposals_only_one_can_publish(database, publication_input):
    _, factory = database
    digest, command = await prepare(factory, publication_input)
    manifest = publication_input[2].model_copy(deep=True)
    manifest.applicability.rationale = "Competing synthetic interpretation"
    async with factory() as db, db.begin():
        second = await store.propose(
            db,
            ACTOR,
            store.ProposeCommand(
                request_key=uuid.uuid4(),
                manifest=manifest,
            ),
        )
    second_command = command.model_copy(update={"request_key": uuid.uuid4()})
    results = await asyncio.gather(
        decide(factory, digest, command),
        decide(factory, second["publication_digest"], second_command),
        return_exceptions=True,
    )
    assert sum(isinstance(r, dict) for r in results) == 1
    assert (
        sum(isinstance(r, review.WorkflowError) and "overlapping" in str(r) for r in results) == 1
    )


async def test_revoke_blocks_fresh_lookup_but_replay_is_only_history(database, publication_input):
    _, factory = database
    digest, command = await prepare(factory, publication_input)
    original = await decide(factory, digest, command)
    revoke = command.model_copy(
        update={
            "request_key": uuid.uuid4(),
            "action": "revoke",
            "expires_at": None,
            "expected_revision": 1,
        }
    )
    await decide(factory, digest, revoke)
    assert await decide(factory, digest, command) == original
    result = await lookup(factory, digest)
    assert result["reason"] == "revoked" and result["facts"] == []
    with pytest.raises(review.WorkflowError, match="revision changed"):
        await decide(factory, digest, command.model_copy(update={"request_key": uuid.uuid4()}))


@pytest.mark.parametrize("action", ["revoke", "accept_representation"])
async def test_changed_representation_invalidates_publication(database, publication_input, action):
    _, factory = database
    digest, command = await prepare(factory, publication_input)
    await decide(factory, digest, command)
    async with factory() as db, db.begin():
        await review.review_draft(
            db,
            ACTOR,
            publication_input[2].draft_digest,
            review.ReviewCommand(
                request_key=uuid.uuid4(),
                expected_revision=1,
                action=action,
                reason="Synthetic superseding review",
                expires_at=datetime.now(UTC) + timedelta(days=2)
                if action == "accept_representation"
                else None,
            ),
        )
    assert (await lookup(factory, digest))["reason"] == "representation_invalidated"


async def test_expired_publication_and_overlong_approval_fail(
    database, publication_input, monkeypatch
):
    _, factory = database
    digest, command = await prepare(factory, publication_input)
    with pytest.raises(review.WorkflowError, match="review validity"):
        await decide(
            factory,
            digest,
            command.model_copy(update={"expires_at": datetime.now(UTC) + timedelta(days=3)}),
        )
    await decide(factory, digest, command)
    later = datetime.now(UTC) + timedelta(days=1, seconds=1)

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return later

    monkeypatch.setattr(store, "datetime", Later)
    assert (await lookup(factory, digest))["reason"] == "expired"


async def test_conditional_unknown_does_not_release_facts(database, publication_input):
    _, factory = database
    publication_input[2].scopes[0].conditions.any_of = [
        [Predicate(field="residency", op="eq", value="resident")]
    ]
    digest, command = await prepare(factory, publication_input)
    await decide(factory, digest, command)
    assert (await lookup(factory, digest))["reason"] == "conditions_unknown"
    assert (await lookup(factory, digest, residency="nonresident"))[
        "reason"
    ] == "conditions_not_met"
    assert (await lookup(factory, digest, residency="resident"))["status"] == "available"


async def test_rollback_and_append_only_events(database, publication_input):
    _, factory = database
    digest, command = await prepare(factory, publication_input)
    with pytest.raises(RuntimeError, match="rollback"):
        async with factory() as db, db.begin():
            await store.decide(db, PUBLISHER, digest, command)
            await db.flush()
            raise RuntimeError("rollback")
    assert (await lookup(factory, digest))["reason"] == "pending"
    await decide(factory, digest, command)
    for table in ("policy_publications", "policy_publication_events"):
        for sql in (f"DELETE FROM {table}", f"UPDATE {table} SET issuer = issuer"):
            with pytest.raises(DBAPIError, match="append-only"):
                async with factory() as db, db.begin():
                    await db.execute(text(sql))


async def test_foreign_issuer_cannot_read_or_decide(database, publication_input):
    _, factory = database
    digest, command = await prepare(factory, publication_input)
    foreign = review.Reviewer(PUBLISHER.subject, "https://other.example/")
    with pytest.raises(review.WorkflowError, match="not found"):
        await decide(factory, digest, command, actor=foreign)
    async with factory() as db, db.begin():
        with pytest.raises(review.WorkflowError, match="not found"):
            await store.read(db, foreign, digest)


async def test_forged_source_reference_cannot_stage_publication(database, publication_input):
    _, factory = database
    await prepare(factory, publication_input)
    publication_input[2].applicability.evidence[0].quote = "Forged evidence"
    with pytest.raises(ValueError, match="quote is absent"):
        async with factory() as db, db.begin():
            await store.propose(
                db,
                ACTOR,
                store.ProposeCommand(request_key=uuid.uuid4(), manifest=publication_input[2]),
            )
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(PolicyPublication)) == 1


async def test_calendar_units_and_reviewed_age_basis_survive_publication(
    database, publication_input
):
    _, factory = database
    manifest = publication_input[2]
    for capability, age_basis in [
        ("adult_entry_ages", "completed_years_at_entry"),
        ("base_ped_wait", None),
    ]:
        manifest.scopes.append(
            FactScope(
                capability=capability,
                conditions=manifest.scopes[0].conditions,
                age_basis=age_basis,
                evidence=manifest.scopes[0].evidence,
                note_mappings=[],
            )
        )
    digest, command = await prepare(factory, publication_input)
    await decide(factory, digest, command)
    async with factory() as db, db.begin():
        ped = await store.lookup(
            db, issuer=ACTOR.issuer, digest=digest, capability="base_ped_wait", context=context()
        )
        age = await store.lookup(
            db, issuer=ACTOR.issuer, digest=digest, capability="adult_entry_ages", context=context()
        )
        assert ped["facts"][0]["value"] == {
            "kind": "waiting_period",
            "count": 36,
            "unit": "calendar_months",
        }
        assert {f["value"]["years"] for f in age["facts"]} == {18, 65}
        assert all(f["value"]["age_basis"] == "completed_years_at_entry" for f in age["facts"])


async def test_republish_after_revoke_needs_new_revision_and_new_receipt(
    database, publication_input
):
    _, factory = database
    digest, command = await prepare(factory, publication_input)
    await decide(factory, digest, command)
    await decide(
        factory,
        digest,
        command.model_copy(
            update={
                "request_key": uuid.uuid4(),
                "expected_revision": 1,
                "action": "revoke",
                "expires_at": None,
            }
        ),
    )
    renewed = await decide(
        factory,
        digest,
        command.model_copy(update={"request_key": uuid.uuid4(), "expected_revision": 2}),
    )
    assert renewed["revision"] == 3
    assert (await lookup(factory, digest))["status"] == "available"


async def test_expiry_exact_boundary_and_requirements_readback(
    database, publication_input, monkeypatch
):
    _, factory = database
    digest, command = await prepare(factory, publication_input)
    await decide(factory, digest, command)
    async with factory() as db, db.begin():
        required = await store.requirements(db, ACTOR, publication_input[2].draft_digest)
        assert not required["production_approved"]
        assert required["supported_capabilities"]["coverage_options"]["missing_typed_fields"] == []
        assert {n["field"] for n in required["notes"]} == {"exclusions", "premium_table"}

    class AtExpiry(datetime):
        @classmethod
        def now(cls, tz=None):
            return command.expires_at

    monkeypatch.setattr(store, "datetime", AtExpiry)
    assert (await lookup(factory, digest))["reason"] == "expired"


async def test_marketing_label_change_cannot_bypass_overlap_lock(database, publication_input):
    _, factory = database
    digest, command = await prepare(factory, publication_input)
    await decide(factory, digest, command)
    draft, sources, manifest = publication_input
    package = draft.source_package.model_dump(mode="json")
    package["product"] = "Another marketing label"
    changed = build_draft(json.dumps(package), sources, as_of=draft.normalized_on)
    changed_manifest = manifest.model_copy(deep=True)
    changed_manifest.draft_digest = assess_draft(
        changed.model_dump_json(), sources, as_of=draft.normalized_on
    )["draft_sha256"]
    second, second_command = await prepare(factory, (changed, sources, changed_manifest))
    with pytest.raises(review.WorkflowError, match="overlapping"):
        await decide(factory, second, second_command)
