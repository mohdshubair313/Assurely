"""Reviewed comparison against isolated Postgres, including concurrent decisions."""

import asyncio
import json
import uuid
from datetime import datetime, timedelta

import httpx
import pytest

from app.api.v1 import policy_publications as api
from app.api.v1.policy_reviews import review_db
from app.db import policy_publication_store as publication
from app.db import reviewed_comparison
from app.db.policy_publication_contract import FactScope, NoteMapping, Predicate, note_id
from app.db.policy_review_store import Reviewer
from app.db.policy_rule_draft import assess_draft, build_draft
from tests.integration.test_policy_publication_workflow import database as _database
from tests.integration.test_policy_publication_workflow import (
    decide,
    prepare,
)
from tests.integration.test_policy_review_workflow import ACTOR, URL
from tests.integration.test_policy_review_workflow import database as _review_database
from tests.unit.test_policy_publication import context
from tests.unit.test_policy_publication import publication_input as _publication_input
from tests.unit.test_policy_review_api import setup as _review_setup
from tests.unit.test_policy_review_api import token

database = _database
review_database = _review_database
publication_input = _publication_input
pytestmark = pytest.mark.skipif(not URL, reason="Isolated policy-review Postgres URL required")


def comparison(items):
    return reviewed_comparison.ComparisonRequest(
        items=[
            reviewed_comparison.ComparisonItem(
                publication_digest=digest, capabilities=capabilities, context=ctx
            )
            for digest, capabilities, ctx in items
        ]
    )


async def preview(factory, request, actor=ACTOR):
    async with factory() as db, db.begin():
        return await reviewed_comparison.compare(db, actor, request)


async def make_family_publication(factory, original_manifest, command):
    manifest = original_manifest.model_copy(deep=True)
    manifest.applicability.cover_basis = "family_floater"
    async with factory() as db, db.begin():
        proposal = await publication.propose(
            db, ACTOR, publication.ProposeCommand(request_key=uuid.uuid4(), manifest=manifest)
        )
    await decide(
        factory,
        proposal["publication_digest"],
        command.model_copy(update={"request_key": uuid.uuid4()}),
    )
    return proposal["publication_digest"]


async def test_reviewed_facts_preserve_scopes_units_and_audit_sources(database, publication_input):
    _, factory = database
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
    digest, command = await prepare(factory, publication_input)
    receipt = await decide(factory, digest, command)
    requested = comparison(
        [(digest, ["coverage_options", "adult_entry_ages", "base_ped_wait"], context())]
    )
    result = await preview(factory, requested)
    assert result["status"] == "complete" and result["scope"] == "internal_review_preview"
    assert result["requires_fresh_lookup"] is True
    assert result["customer_delivery_authorized"] is False
    caps = {item["capability"]: item for item in result["items"][0]["capabilities"]}
    assert caps["coverage_options"]["facts"][0]["value"]["amounts"] == [50_000_000, 100_000_000]
    assert caps["base_ped_wait"]["facts"][0]["value"] == {
        "kind": "waiting_period",
        "count": 36,
        "unit": "calendar_months",
    }
    assert {f["value"]["years"] for f in caps["adult_entry_ages"]["facts"]} == {18, 65}
    for cap in caps.values():
        assert cap["status"] == "available"
        assert cap["conditions"] == {"any_of": [[]]}
        assert cap["applicability"]["cover_basis"] == "individual"
        assert cap["scope_review"]["last_verified"] == receipt["recorded_at"][:10]
        assert cap["scope_review"]["verification_event_id"] == receipt["event_id"]
        assert cap["scope_review"]["applicability_evidence"][0]["sha256"]
        assert cap["scope_review"]["condition_evidence"][0]["url"].startswith("https://")
        for fact in cap["facts"]:
            assert fact["source"][0]["sha256"]
            assert fact["source"][0]["url"].startswith("https://")
            assert fact["last_verified"] == receipt["recorded_at"][:10]
            assert fact["verification_event_id"] == receipt["event_id"]
    text = str(result).lower()
    assert "premium_estimate" not in text and "eligible" not in text


async def test_partial_results_do_not_turn_unknown_or_absent_facts_into_values(
    database, publication_input
):
    _, factory = database
    publication_input[2].scopes[0].conditions.any_of = [
        [Predicate(field="residency", op="eq", value="resident")]
    ]
    digest, command = await prepare(factory, publication_input)
    await decide(factory, digest, command)
    family = await make_family_publication(factory, publication_input[2], command)
    request = comparison(
        [
            (
                family,
                ["coverage_options"],
                context(cover_basis="family_floater", residency="resident"),
            ),
            (digest, ["coverage_options", "base_ped_wait"], context()),
            ("f" * 64, ["coverage_options"], context()),
        ]
    )
    result = await preview(factory, request)
    assert result["status"] == "partial"
    assert [entry["publication_digest"] for entry in result["items"]] == [family, digest, "f" * 64]
    assert result["items"][0]["capabilities"][0]["status"] == "available"
    assert result["items"][1]["capabilities"][0]["reason"] == "conditions_unknown"
    assert result["items"][1]["capabilities"][1]["reason"] == "capability_not_published"
    assert result["items"][2]["capabilities"][0]["reason"] == "not_found"
    for entry in result["items"][1:]:
        assert all(not cap["facts"] for cap in entry["capabilities"])


async def test_condition_mapping_retains_its_own_reviewed_evidence(database, publication_input):
    _, factory = database
    draft, sources, manifest = publication_input
    package = draft.source_package.model_dump(mode="json")
    field = next(f for f in package["fields"] if f["name"] == "sum_insured_options")
    field["conditions"] = ["Resident applicants only"]
    changed = build_draft(json.dumps(package), sources, as_of=draft.normalized_on)
    manifest = manifest.model_copy(deep=True)
    manifest.draft_digest = assess_draft(
        changed.model_dump_json(), sources, as_of=draft.normalized_on
    )["draft_sha256"]
    scope = manifest.scopes[0]
    scope.conditions.any_of = [[Predicate(field="residency", op="eq", value="resident")]]
    scope.note_mappings = [
        NoteMapping(
            note_sha256=note_id("sum_insured_options", "conditions", 0, "Resident applicants only"),
            disposition="condition",
            rationale="Synthetic resident interpretation",
            evidence=scope.evidence,
        )
    ]
    digest, command = await prepare(factory, (changed, sources, manifest))
    await decide(factory, digest, command)
    result = await preview(
        factory, comparison([(digest, ["coverage_options"], context(residency="resident"))])
    )
    note = result["items"][0]["capabilities"][0]["scope_review"]["condition_note_mappings"][0]
    assert note["note_sha256"] == scope.note_mappings[0].note_sha256
    assert note["disposition"] == "condition"
    assert note["evidence"][0]["sha256"] and note["evidence"][0]["pdf_page"] == 1


async def test_revocation_and_foreign_issuer_never_return_historical_facts(
    database, publication_input
):
    _, factory = database
    digest, command = await prepare(factory, publication_input)
    await decide(factory, digest, command)
    request = comparison([(digest, ["coverage_options"], context())])
    assert (await preview(factory, request))["status"] == "complete"
    foreign = Reviewer(ACTOR.subject, "https://other.example/")
    other = await preview(factory, request, foreign)
    assert other["status"] == "unavailable"
    assert other["items"][0]["capabilities"][0]["reason"] == "not_found"
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
    revoked = await preview(factory, request)
    assert revoked["status"] == "unavailable"
    assert revoked["items"][0]["capabilities"][0]["reason"] == "revoked"
    assert revoked["items"][0]["capabilities"][0]["facts"] == []


async def test_expiry_during_preview_removes_previously_collected_facts(
    database, publication_input, monkeypatch
):
    _, factory = database
    digest, command = await prepare(factory, publication_input)
    await decide(factory, digest, command)
    actual_state = publication._state
    calls = 0

    async def expires_late(db, row):
        nonlocal calls
        calls += 1
        status, event = await actual_state(db, row)
        return ("expired", event) if calls >= 3 else (status, event)

    monkeypatch.setattr(publication, "_state", expires_late)
    result = await preview(factory, comparison([(digest, ["coverage_options"], context())]))
    assert result["status"] == "unavailable"
    assert result["items"][0]["capabilities"][0]["reason"] == "expired"
    assert result["items"][0]["capabilities"][0]["facts"] == []


async def test_final_shared_timestamp_rejects_later_expiry(
    database, publication_input, monkeypatch
):
    _, factory = database
    digest, command = await prepare(factory, publication_input)
    await decide(factory, digest, command)
    after_expiry = command.expires_at + timedelta(seconds=1)

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return after_expiry

    monkeypatch.setattr(reviewed_comparison, "datetime", Later)
    result = await preview(factory, comparison([(digest, ["coverage_options"], context())]))
    assert result["status"] == "unavailable"
    assert result["items"][0]["capabilities"][0]["reason"] == "expired"
    assert result["items"][0]["capabilities"][0]["facts"] == []


async def test_revocation_waits_for_preview_transaction_and_fresh_preview_reflects_it(
    database, publication_input
):
    _, factory = database
    digest, command = await prepare(factory, publication_input)
    await decide(factory, digest, command)
    request = comparison([(digest, ["coverage_options"], context())])
    revoke = command.model_copy(
        update={
            "request_key": uuid.uuid4(),
            "expected_revision": 1,
            "action": "revoke",
            "expires_at": None,
        }
    )
    async with factory() as db, db.begin():
        result = await reviewed_comparison.compare(db, ACTOR, request)
        assert result["status"] == "complete" and not result["customer_delivery_authorized"]
        task = asyncio.create_task(decide(factory, digest, revoke))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), timeout=0.2)
    await asyncio.wait_for(task, timeout=5)
    assert (await preview(factory, request))["items"][0]["capabilities"][0]["reason"] == "revoked"


async def test_opposite_input_order_does_not_deadlock_concurrent_previews(
    database, publication_input
):
    _, factory = database
    digest, command = await prepare(factory, publication_input)
    await decide(factory, digest, command)
    draft, sources, manifest = publication_input
    package = draft.source_package.model_dump(mode="json")
    next(field for field in package["fields"] if field["name"] == "uin")["proposed_value"] = (
        "OTHER-UIN"
    )
    other_draft = build_draft(json.dumps(package), sources, as_of=draft.normalized_on)
    other_manifest = manifest.model_copy(deep=True)
    other_manifest.draft_digest = assess_draft(
        other_draft.model_dump_json(), sources, as_of=draft.normalized_on
    )["draft_sha256"]
    other, other_command = await prepare(factory, (other_draft, sources, other_manifest))
    await decide(factory, other, other_command)
    a = (digest, ["coverage_options"], context())
    b = (other, ["coverage_options"], context())
    results = await asyncio.wait_for(
        asyncio.gather(preview(factory, comparison([a, b])), preview(factory, comparison([b, a]))),
        timeout=10,
    )
    assert all(result["status"] == "complete" for result in results)
    assert [entry["publication_digest"] for entry in results[0]["items"]] == [digest, other]
    assert [entry["publication_digest"] for entry in results[1]["items"]] == [other, digest]


async def test_explicit_transaction_is_required(database):
    _, factory = database
    async with factory() as db:
        with pytest.raises(RuntimeError, match="explicit transaction"):
            await reviewed_comparison.compare(
                db, ACTOR, comparison([("a" * 64, ["coverage_options"], context())])
            )


async def test_signed_http_preview_uses_fresh_database_decision(
    database, publication_input, monkeypatch
):
    _, factory = database
    digest, command = await prepare(factory, publication_input)
    await decide(factory, digest, command)
    app, _, key, settings = _review_setup.__wrapped__(monkeypatch)
    settings.auth_issuer = ACTOR.issuer
    app.include_router(api.router, prefix="/v1")

    async def real_db():
        async with factory() as db, db.begin():
            yield db

    app.dependency_overrides[review_db] = real_db
    request = comparison([(digest, ["coverage_options"], context())])
    body = request.model_dump(mode="json")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        result = await client.post(
            "/v1/policy-publications/comparisons", json=body, headers=token(key, iss=ACTOR.issuer)
        )
        assert result.status_code == 200 and result.json()["status"] == "complete"
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
        result = await client.post(
            "/v1/policy-publications/comparisons", json=body, headers=token(key, iss=ACTOR.issuer)
        )
        assert result.status_code == 200 and result.json()["status"] == "unavailable"
        assert result.json()["items"][0]["capabilities"][0]["reason"] == "revoked"
