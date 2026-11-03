"""Reviewed term import, application schema and graph gate in disposable Postgres."""

import asyncio
import importlib.util
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1 import policy_publications as api
from app.api.v1.message import build_message_response
from app.api.v1.policy_reviews import review_db
from app.db import policy_publication_store as publication
from app.db import policy_review_store as review
from app.db import reviewed_comparison, reviewed_policy_terms
from app.db.policy_publication_contract import FactScope
from app.db.reviewed_delivery import check_reviewed_delivery
from app.graph.nodes import compare_verify, explanation_report, guardrail
from app.models.db.policy_document import PolicyDocument
from app.models.db.policy_terms import PolicyTerms
from tests.integration.test_policy_publication_workflow import PUBLISHER, decide, prepare
from tests.integration.test_policy_review_workflow import ACTOR, URL
from tests.unit.test_policy_publication import context
from tests.unit.test_policy_publication import publication_input as _publication_input
from tests.unit.test_policy_review_api import SUBJECT, token
from tests.unit.test_policy_review_api import setup as _review_setup

publication_input = _publication_input
pytestmark = pytest.mark.skipif(not URL, reason="Isolated policy-review Postgres URL required")
MIGRATIONS = Path(__file__).parents[2] / "alembic/versions"


@pytest_asyncio.fixture
async def database():
    if make_url(URL).database != "policy_review_test_terms":
        raise RuntimeError("This test requires the dedicated policy_review_test_terms database")
    engine = create_async_engine(URL)
    modules = []
    for path in sorted(MIGRATIONS.glob("*.py")):
        spec = importlib.util.spec_from_file_location("test_" + path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)

    def migrate(conn):
        with Operations.context(MigrationContext.configure(conn)):
            for module in modules:
                module.upgrade()

    async with engine.begin() as connection:
        await connection.run_sync(migrate)
    terms_migration = next(m for m in modules if m.revision == "006_reviewed_policy_terms")
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    yield engine, factory, terms_migration
    # The container and this named database are dedicated to these tests only.
    async with engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


def request(digest, **changes):
    return reviewed_comparison.ComparisonRequest(
        items=[
            reviewed_comparison.ComparisonItem(
                publication_digest=digest,
                capabilities=["coverage_options"],
                context=context(**changes),
            )
        ]
    )


async def stage_and_publish(factory, publication_input):
    digest, decision = await prepare(factory, publication_input)
    receipt = await decide(factory, digest, decision)
    cmd = reviewed_policy_terms.ImportCommand(
        request_key=uuid.uuid4(), publication_event_id=uuid.UUID(receipt["event_id"])
    )
    return digest, decision, cmd


async def import_terms(factory, digest, command, actor=PUBLISHER):
    async with factory() as db, db.begin():
        return await reviewed_policy_terms.import_terms(db, actor, digest, command)


async def compare(factory, digest, **changes):
    async with factory() as db, db.begin():
        return await reviewed_comparison.compare_terms(db, ACTOR.issuer, request(digest, **changes))


async def test_import_stores_exact_terms_and_graph_keeps_delivery_held(
    database, publication_input, monkeypatch
):
    _, factory, _ = database
    digest, _, command = await stage_and_publish(factory, publication_input)
    before = await compare(factory, digest)
    assert before["items"][0]["capabilities"][0]["reason"] == "terms_not_imported"
    receipt = await import_terms(factory, digest, command)
    comparison = await compare(factory, digest)
    fact = comparison["items"][0]["capabilities"][0]["facts"][0]
    assert fact["value"]["amounts"] == [50_000_000, 100_000_000]
    assert fact["policy_terms_id"] == receipt["policy_terms_id"]
    assert fact["source"][0]["sha256"] and fact["last_verified"]
    async with factory() as db:
        term = await db.get(PolicyTerms, uuid.UUID(receipt["policy_terms_id"]))
        assert term.record_kind == "reviewed_v1"
        assert term.policy_document_id is None and term.effective_date is None
        assert term.sum_insured_min is None and term.waiting_period_days_preexisting is None
        # The old comparison's inner join cannot pick reviewed records.
        assert (
            await db.execute(
                select(PolicyTerms).join(
                    PolicyDocument, PolicyTerms.policy_document_id == PolicyDocument.id
                )
            )
        ).all() == []
    monkeypatch.setattr(
        compare_verify,
        "get_settings",
        lambda: SimpleNamespace(environment="production", auth_issuer=ACTOR.issuer),
    )
    monkeypatch.setattr(compare_verify, "AsyncSessionLocal", factory)
    output = await compare_verify.compare_verify_node(
        {"reviewed_comparison_request": request(digest).model_dump(mode="json")}
    )
    assert output["draft_output"]["reviewed_comparison"]["status"] == "complete"
    assert output["draft_output"]["publication_gate"] == "blocked"
    checked = await guardrail.guardrail_node(output)
    assert checked["approved"] is False and checked["escalation"] is True
    rendered = await explanation_report.explanation_report_node({
        **output, **checked, "intent": "health",
        "reviewed_comparison_request": request(digest).model_dump(mode="json"),
    })
    report = rendered["output"]
    assert report["report_status"] == "reviewed_report_held"
    assert report["claim_support"]["supported"] is True
    assert report["sentences"][0]["citations"][0]["policy_terms_id"] == receipt["policy_terms_id"]
    response = build_message_response("synthetic", {**output, **checked, **rendered})
    assert response.delivery_hold and response.draft_output == {} and response.output == {}


async def test_import_requires_exact_live_event_and_replay_never_releases(
    database, publication_input
):
    _, factory, _ = database
    digest, decision, command = await stage_and_publish(factory, publication_input)
    bad = command.model_copy(update={"publication_event_id": uuid.uuid4()})
    with pytest.raises(review.WorkflowError, match="matching publication"):
        await import_terms(factory, digest, bad)
    receipt = await import_terms(factory, digest, command)
    comparison = await compare(factory, digest)
    report_state = {
        "intent": "health", "reviewed_comparison_request": request(digest).model_dump(mode="json"),
        "draft_output": {"stage": "compare_verify", "reviewed_comparison": comparison},
    }
    report_state.update(await explanation_report.explanation_report_node(report_state))
    async with factory() as db, db.begin():
        check = await check_reviewed_delivery(db, ACTOR.issuer, report_state)
    assert check.evidence_current and check.reason == "advisor_authorization_required"
    await decide(
        factory,
        digest,
        decision.model_copy(
            update={
                "request_key": uuid.uuid4(),
                "expected_revision": 1,
                "action": "revoke",
                "expires_at": None,
            }
        ),
    )
    assert await import_terms(factory, digest, command) == receipt
    result = await compare(factory, digest)
    assert result["status"] == "unavailable"
    assert result["items"][0]["capabilities"][0]["reason"] == "revoked"
    async with factory() as db, db.begin():
        check = await check_reviewed_delivery(db, ACTOR.issuer, report_state)
    assert not check.evidence_current
    with pytest.raises(review.WorkflowError, match="matching publication"):
        await import_terms(
            factory, digest, command.model_copy(update={"request_key": uuid.uuid4()})
        )


async def test_expiry_during_import_leaves_no_term_snapshot(
    database, publication_input, monkeypatch
):
    _, factory, _ = database
    digest, _, command = await stage_and_publish(factory, publication_input)
    original = publication._state
    count = 0

    async def expires_after_validation(db, row):
        nonlocal count
        count += 1
        status, event = await original(db, row)
        return ("expired", event) if count >= 2 else (status, event)

    monkeypatch.setattr(publication, "_state", expires_after_validation)
    with pytest.raises(review.WorkflowError, match="expired or changed"):
        await import_terms(factory, digest, command)
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(PolicyTerms)) == 0


async def test_duplicate_import_is_idempotent_and_transactional(database, publication_input):
    _, factory, _ = database
    digest, _, command = await stage_and_publish(factory, publication_input)
    with pytest.raises(RuntimeError, match="rollback"):
        async with factory() as db, db.begin():
            await reviewed_policy_terms.import_terms(db, PUBLISHER, digest, command)
            await db.flush()
            raise RuntimeError("rollback")
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(PolicyTerms)) == 0
    results = await asyncio.gather(*(import_terms(factory, digest, command) for _ in range(4)))
    assert all(result == results[0] for result in results)
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(PolicyTerms)) == 1
    with pytest.raises(review.WorkflowError, match="different request"):
        await import_terms(
            factory, digest, command.model_copy(update={"publication_event_id": uuid.uuid4()})
        )


async def test_snapshot_is_immutable_and_downgrade_refuses_to_destroy_it(
    database, publication_input
):
    engine, factory, migration = database
    digest, _, command = await stage_and_publish(factory, publication_input)
    await import_terms(factory, digest, command)
    for sql in (
        "UPDATE policy_terms SET reviewed_facts_json = '{}'::jsonb",
        "DELETE FROM policy_terms",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            async with factory() as db, db.begin():
                await db.execute(text(sql))

    def downgrade(conn):
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()

    with pytest.raises(DBAPIError, match="Refusing downgrade"):
        async with engine.begin() as connection:
            await connection.run_sync(downgrade)
    assert (await compare(factory, digest))["status"] == "complete"


async def test_applicability_and_issuer_still_gate_imported_values(database, publication_input):
    _, factory, _ = database
    digest, _, command = await stage_and_publish(factory, publication_input)
    await import_terms(factory, digest, command)
    no_match = await compare(factory, digest, transaction="renewal")
    assert no_match["items"][0]["capabilities"][0]["reason"] == "not_applicable"
    async with factory() as db, db.begin():
        result = await reviewed_comparison.compare_terms(
            db, "https://other.example/", request(digest)
        )
        assert result["items"][0]["capabilities"][0]["reason"] == "not_found"


async def test_existing_term_tampering_is_detected_before_lookup(database, publication_input):
    _, factory, _ = database
    digest, _, command = await stage_and_publish(factory, publication_input)
    # Simulate a pre-existing bad insert, before the guarded importer is called.
    async with factory() as db, db.begin():
        await db.execute(
            text(
                "INSERT INTO policy_terms (id, record_kind, version_hash, "
                "publication_digest, reviewed_facts_json) VALUES "
                "(:id, 'reviewed_v1', :digest, :digest, '{}'::jsonb)"
            ),
            {"id": uuid.uuid4(), "digest": digest},
        )
    with pytest.raises(review.WorkflowError, match="integrity"):
        await import_terms(factory, digest, command)
    result = await compare(factory, digest)
    cap = result["items"][0]["capabilities"][0]
    assert cap["reason"] == "integrity_check_failed" and cap["facts"] == []


async def test_import_preserves_reviewed_age_basis_and_calendar_wait(database, publication_input):
    _, factory, _ = database
    manifest = publication_input[2]
    for capability, basis in [
        ("adult_entry_ages", "completed_years_at_entry"),
        ("base_ped_wait", None),
    ]:
        manifest.scopes.append(
            FactScope(
                capability=capability,
                age_basis=basis,
                conditions=manifest.scopes[0].conditions,
                evidence=manifest.scopes[0].evidence,
                note_mappings=[],
            )
        )
    digest, _, command = await stage_and_publish(factory, publication_input)
    await import_terms(factory, digest, command)
    req = reviewed_comparison.ComparisonRequest(
        items=[
            reviewed_comparison.ComparisonItem(
                publication_digest=digest,
                capabilities=["adult_entry_ages", "base_ped_wait"],
                context=context(),
            )
        ]
    )
    async with factory() as db, db.begin():
        result = await reviewed_comparison.compare_terms(db, ACTOR.issuer, req)
    caps = {cap["capability"]: cap for cap in result["items"][0]["capabilities"]}
    assert all(
        f["value"]["age_basis"] == "completed_years_at_entry"
        for f in caps["adult_entry_ages"]["facts"]
    )
    assert caps["base_ped_wait"]["facts"][0]["value"] == {
        "kind": "waiting_period",
        "count": 36,
        "unit": "calendar_months",
    }
    report = (await explanation_report.explanation_report_node({
        "intent": "health", "reviewed_comparison_request": req.model_dump(mode="json"),
        "draft_output": {"stage": "compare_verify", "reviewed_comparison": result},
    }))["output"]
    assert report["report_status"] == "reviewed_report_held"
    assert "36 calendar months" in report["reply"]
    assert "completed years at entry" in report["reply"]
    assert len(report["sentences"]) == 3


async def test_signed_http_import_and_graph_lookup_use_same_persisted_terms(
    database, publication_input, monkeypatch
):
    _, factory, _ = database
    digest, _, command = await stage_and_publish(factory, publication_input)
    app, _, key, settings = _review_setup.__wrapped__(monkeypatch)
    settings.auth_issuer = ACTOR.issuer
    settings.policy_publisher_subjects = [str(SUBJECT)]
    app.include_router(api.router, prefix="/v1")

    async def real_db():
        async with factory() as db, db.begin():
            yield db

    app.dependency_overrides[review_db] = real_db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/v1/policy-publications/{digest}/term-import",
            json=command.model_dump(mode="json"),
            headers=token(key, iss=ACTOR.issuer),
        )
    assert response.status_code == 200
    terms_id = response.json()["policy_terms_id"]
    monkeypatch.setattr(
        compare_verify,
        "get_settings",
        lambda: SimpleNamespace(environment="production", auth_issuer=ACTOR.issuer),
    )
    monkeypatch.setattr(compare_verify, "AsyncSessionLocal", factory)
    node = await compare_verify.compare_verify_node(
        {"reviewed_comparison_request": request(digest).model_dump(mode="json")}
    )
    facts = node["draft_output"]["reviewed_comparison"]["items"][0]["capabilities"][0]["facts"]
    assert facts[0]["policy_terms_id"] == terms_id
    assert node["draft_output"]["publication_gate"] == "blocked"


async def test_migration_preserves_existing_legacy_rows_and_can_reverse_before_import():
    if make_url(URL).database != "policy_review_test_terms":
        raise RuntimeError("This test requires the dedicated policy_review_test_terms database")
    engine = create_async_engine(URL)
    modules = []
    for path in sorted(MIGRATIONS.glob("*.py")):
        spec = importlib.util.spec_from_file_location("legacy_" + path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)

    def run_pre006(conn):
        with Operations.context(MigrationContext.configure(conn)):
            for module in modules[:-1]:
                module.upgrade()

    def run_migration(conn, operation):
        with Operations.context(MigrationContext.configure(conn)):
            operation()

    document_id, term_id = uuid.uuid4(), uuid.uuid4()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(run_pre006)
            await conn.execute(
                text(
                    "INSERT INTO policy_documents "
                    "(id, insurer, product_name, version_hash) "
                    "VALUES (:id, 'Fixture', 'Example', :hash)"
                ),
                {"id": document_id, "hash": "a" * 64},
            )
            await conn.execute(
                text(
                    "INSERT INTO policy_terms "
                    "(id, policy_document_id, version_hash, entry_age_min, effective_date) "
                    "VALUES (:id, :doc, :hash, 18, '2024-01-01')"
                ),
                {"id": term_id, "doc": document_id, "hash": "b" * 64},
            )
            await conn.run_sync(run_migration, modules[-1].upgrade)
            row = (
                await conn.execute(
                    text(
                        "SELECT policy_document_id, entry_age_min, effective_date, "
                        "record_kind, publication_digest, reviewed_facts_json "
                        "FROM policy_terms WHERE id = :id"
                    ),
                    {"id": term_id},
                )
            ).one()
            assert row.policy_document_id == document_id and row.entry_age_min == 18
            assert row.effective_date.isoformat() == "2024-01-01" and row.record_kind == "legacy"
            assert row.publication_digest is None and row.reviewed_facts_json is None
            await conn.run_sync(run_migration, modules[-1].downgrade)
            assert (
                await conn.execute(
                    text("SELECT entry_age_min FROM policy_terms WHERE id = :id"), {"id": term_id}
                )
            ).scalar_one() == 18
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await engine.dispose()
