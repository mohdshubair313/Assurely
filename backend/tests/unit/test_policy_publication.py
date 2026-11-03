"""Publication contract: explicit applicability, three-state rules, scoped evidence."""

import json
from copy import deepcopy
from datetime import date

import pytest
from pydantic import ValidationError

from app.db import policy_review_store as review
from app.db.policy_publication_contract import (
    Conditions,
    DateWindow,
    LookupContext,
    Predicate,
    PublicationManifest,
    applicability_result,
    note_id,
    validate_evidence,
    validate_manifest,
)
from app.db.policy_publication_store import _overlaps
from app.db.policy_rule_draft import assess_draft, build_draft
from tests.unit.test_policy_rule_draft import candidate as source_candidate
from tests.unit.test_policy_rule_draft import propose


@pytest.fixture
def publication_input():
    package, sources = source_candidate.__wrapped__()
    for name, value, unit in [
        ("uin", "SYNTHETIC-UIN", "text"),
        ("variant", "Synthetic base", "text"),
        ("effective_date", "2026-01-01", "date"),
        ("expiry_date", "2026-12-31", "date"),
        ("sum_insured_options", "500000; 1000000", "INR"),
        ("adult_entry_age_min", "18", "years"),
        ("adult_entry_age_max", "65", "years"),
        ("ped_waiting_period", "36", "calendar_months"),
    ]:
        propose(package, name, value, unit, notes=[])
    draft = build_draft(json.dumps(package), sources, as_of=date(2026, 11, 2))
    digest = assess_draft(draft.model_dump_json(), sources, as_of=date(2026, 11, 2))["draft_sha256"]
    ref = package["fields"][0]["references"][0]
    raw = {
        "draft_digest": digest,
        "applicability": {
            "date_basis": "policy_issue_date",
            "window": {"start": "2026-01-01", "end_kind": "inclusive", "end": "2026-12-31"},
            "cover_basis": "individual",
            "selected_options": [],
            "evidence": [ref],
            "rationale": "Synthetic issue-date applicability; not a real insurer approval",
        },
        "scopes": [
            {
                "capability": "coverage_options",
                "conditions": {"any_of": [[]]},
                "evidence": [ref],
                "note_mappings": [],
            }
        ],
        "identity_notes": [],
        "source_review": "Synthetic source-authenticity test record",
    }
    return draft, sources, PublicationManifest.model_validate_json(json.dumps(raw))


def context(**changes):
    return LookupContext.model_validate_json(
        json.dumps(
            {
                "transaction": "issue",
                "transaction_date": "2026-06-01",
                "cover_basis": "individual",
                "selected_options": [],
                **changes,
            }
        )
    )


@pytest.mark.parametrize("actual,expected", [(None, None), (False, False), (True, True), (1, None)])
def test_predicate_is_three_valued_and_type_strict(actual, expected):
    predicate = Predicate(field="portability", op="eq", value=True)
    assert predicate.evaluate({"portability": actual}) is expected


def test_condition_boolean_algebra_does_not_treat_unknown_as_true():
    a = {"field": "portability", "op": "eq", "value": True}
    b = {"field": "continuity", "op": "eq", "value": True}
    conjunction = Conditions(any_of=[[a, b]])
    disjunction = Conditions(any_of=[[a], [b]])
    assert conjunction.evaluate({"portability": False}) is False
    assert conjunction.evaluate({"portability": True}) is None
    assert disjunction.evaluate({"portability": True}) is True
    assert disjunction.evaluate({"portability": False}) is None
    assert Conditions(any_of=[[]]).evaluate({}) is True


@pytest.mark.parametrize(
    "bad",
    [
        {"field": "entry_age_years", "op": "gte", "value": True},
        {"field": "entry_age_years", "op": "gte", "value": "18"},
        {"field": "entry_age_years", "op": "gte", "value": -1},
        {"field": "portability", "op": "gte", "value": True},
        {"field": "zone", "op": "eq", "value": False},
        {"field": "eval", "op": "eq", "value": "__import__('os')"},
    ],
)
def test_unsupported_conditions_fail_validation(bad):
    with pytest.raises(ValidationError):
        Predicate.model_validate(bad)


@pytest.mark.parametrize(
    "day,expected",
    [
        ("2025-12-31", "not_applicable"),
        ("2026-01-01", "applicable"),
        ("2026-12-31", "applicable"),
        ("2027-01-01", "not_applicable"),
    ],
)
def test_inclusive_transaction_dates(publication_input, day, expected):
    assert applicability_result(publication_input[2], context(transaction_date=day)) == expected


@pytest.mark.parametrize(
    "change",
    [
        {"transaction": "renewal"},
        {"cover_basis": "family_floater"},
        {"selected_options": ["optional-ped"]},
    ],
)
def test_schedule_scope_cannot_be_guessed(publication_input, change):
    assert applicability_result(publication_input[2], context(**change)) == "not_applicable"


def test_unknown_end_cannot_publish_but_explicit_no_end_can(publication_input):
    draft, _, manifest = publication_input
    manifest.applicability.window = DateWindow(start=date(2026, 1, 1), end_kind="unknown")
    with pytest.raises(ValueError, match="Unknown applicability"):
        validate_manifest(manifest, draft)
    manifest.applicability.window.end_kind = "no_declared_end"
    validate_manifest(manifest, draft)


def test_supported_facts_and_original_source_quotes(publication_input):
    draft, blobs, manifest = publication_input
    validate_manifest(manifest, draft)
    validate_evidence(
        manifest, draft, {s.sha256: blobs[s.id] for s in draft.source_package.sources}
    )
    manifest.applicability.evidence[0].quote = "Not in the pinned PDF"
    with pytest.raises(ValueError, match="quote is absent"):
        validate_evidence(
            manifest, draft, {s.sha256: blobs[s.id] for s in draft.source_package.sources}
        )


def test_every_note_requires_mapping_and_conditions_cannot_disappear(publication_input):
    draft, _, manifest = publication_input
    field = next(f for f in draft.source_package.fields if f.name == "sum_insured_options")
    field.conditions = ["Resident only"]
    with pytest.raises(ValueError, match="exact mapping"):
        validate_manifest(manifest, draft)
    raw = manifest.model_dump(mode="json")
    mapping = {
        "note_sha256": note_id(field.name, "conditions", 0, "Resident only"),
        "disposition": "condition",
        "rationale": "Requires resident scope",
        "evidence": raw["applicability"]["evidence"],
    }
    raw["scopes"][0]["note_mappings"] = [mapping]
    with pytest.raises(ValueError, match="unconditional"):
        validate_manifest(PublicationManifest.model_validate_json(json.dumps(raw)), draft)
    raw["scopes"][0]["conditions"] = {
        "any_of": [[{"field": "residency", "op": "eq", "value": "resident"}]]
    }
    validate_manifest(PublicationManifest.model_validate_json(json.dumps(raw)), draft)


def test_missing_fact_and_unsupported_capability_block(publication_input):
    draft, _, manifest = publication_input
    missing = deepcopy(draft)
    next(f for f in missing.fields if f.name == "sum_insured_options").status = "unavailable"
    with pytest.raises(ValueError, match="complete typed"):
        validate_manifest(manifest, missing)
    raw = manifest.model_dump(mode="json")
    raw["scopes"][0]["capability"] = "premium"
    with pytest.raises(ValidationError):
        PublicationManifest.model_validate_json(json.dumps(raw))


def test_digest_binds_every_interpretation(publication_input):
    payload = publication_input[2].model_dump(mode="json")
    before = review._hash(payload)
    payload["applicability"]["date_basis"] = "policy_renewal_date"
    assert review._hash(payload) != before


def test_overlap_boundaries_are_inclusive_and_option_specific(publication_input):
    manifest = publication_input[2]
    other = manifest.model_copy(deep=True)
    other.applicability.window = DateWindow(start=date(2026, 12, 31), end_kind="no_declared_end")
    assert _overlaps(manifest, other)
    other.applicability.window.start = date(2027, 1, 1)
    assert not _overlaps(manifest, other)
    other.applicability.window.start = date(2026, 12, 31)
    other.applicability.selected_options = ["optional-benefit"]
    assert not _overlaps(manifest, other)
