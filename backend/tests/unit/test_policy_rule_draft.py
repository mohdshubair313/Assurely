"""Normalization must preserve unknowns, units and evidence without self-approval."""

import hashlib
import io
import json
from copy import deepcopy
from datetime import date

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.db.policy_rule_draft import assess_draft, build_draft
from app.db.source_review import FIELDS

TODAY = date(2026, 10, 30)


@pytest.fixture
def candidate():
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=300)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
    })
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 100 Td (Synthetic contract-test evidence) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    content = output.getvalue()
    package = {
        "format_version": "policy-source-review-v1",
        "insurer": "Synthetic insurer", "product": "Synthetic policy",
        "review_status": "pending_human_review",
        "sources": [{
            "id": "wording", "url": "https://example.com/synthetic.pdf",
            "sha256": hashlib.sha256(content).hexdigest(),
            "accessed_on": "2026-10-28", "page_count": 1,
        }],
        "fields": [
            {"name": name, "status": "missing", "unresolved": ["Source review pending"]}
            for name in sorted(FIELDS)
        ],
    }
    return package, {"wording": content}


def propose(package, name, value, unit, *, notes=None, conditions=None):
    field = next(f for f in package["fields"] if f["name"] == name)
    field.update(
        status="extracted", proposed_value=value, unit=unit,
        references=[{
            "source_id": "wording", "pdf_page": 1, "clause": "Synthetic fixture",
            "quote": "Synthetic contract-test evidence",
        }],
        unresolved=notes if notes is not None else ["Pending human review"],
        conditions=conditions or [],
    )


def build(candidate):
    package, sources = candidate
    return build_draft(json.dumps(package), sources, as_of=TODAY)


def field(draft, name):
    return next(f for f in draft.fields if f.name == name)


def test_calendar_months_are_never_normalized_to_days(candidate):
    propose(candidate[0], "ped_waiting_period", "36", "calendar_months",
            conditions=["Continuity credits and selected optional cover apply"])
    draft = build(candidate)
    value = field(draft, "ped_waiting_period").value
    assert value.count == 36 and value.unit == "calendar_months"
    assert "1095" not in draft.model_dump_json()
    assert draft.source_package.fields == build(candidate).source_package.fields
    preview = assess_draft(draft.model_dump_json(), candidate[1], as_of=TODAY)
    assert any(b["code"] == "conditions_require_mapping" for b in preview["blockers"])


def test_missing_is_not_zero_no_exclusions_or_unbounded(candidate):
    draft = build(candidate)
    for name in ["premium_table", "exclusions", "adult_entry_age_max", "expiry_date"]:
        value = field(draft, name)
        assert value.status == "unavailable" and value.value is None
    preview = assess_draft(draft.model_dump_json(), candidate[1], as_of=TODAY)
    assert not preview["approved_for_import"] and not preview["production_approved"]


@pytest.mark.parametrize("source_value", ["Lifelong", "No maximum entry age limit"])
def test_explicit_unbounded_age_is_preserved(candidate, source_value):
    propose(candidate[0], "adult_entry_age_max", source_value, "years")
    value = field(build(candidate), "adult_entry_age_max").value
    assert value.bound == "unbounded" and value.years is None


def test_discrete_coverage_keeps_exact_paise_and_gaps(candidate):
    propose(candidate[0], "sum_insured_options", "500000; 750000.25; 1000000", "INR")
    value = field(build(candidate), "sum_insured_options").value
    assert value.amounts == [50_000_000, 75_000_025, 100_000_000]
    assert value.interpolation == "not_authorized"
    assert 60_000_000 not in value.amounts


@pytest.mark.parametrize("value", [
    "5L", "5,00,000", "1e6", "NaN", "Infinity", "500000.001", "-500000", "0",
    "500000;500000.00", "500000;", "500000 to 1000000",
])
def test_ambiguous_or_invalid_amounts_require_interpretation(candidate, value):
    propose(candidate[0], "sum_insured_options", value, "INR")
    result = field(build(candidate), "sum_insured_options")
    assert result.status == "needs_interpretation" and result.value is None


@pytest.mark.parametrize("name,value,unit", [
    ("adult_entry_age_min", "Lifelong", "years"),
    ("adult_entry_age_max", "unknown", "years"),
    ("ped_waiting_period", "3 years", "calendar_months"),
    ("ped_waiting_period", "-1", "days"),
    ("exclusions", "No exclusions", "text"),
    ("premium_table", '{"all": 0}', "text"),
    ("uin", " ", "text"),
])
def test_unsupported_semantics_cannot_become_executable_rules(candidate, name, value, unit):
    propose(candidate[0], name, value, unit)
    assert field(build(candidate), name).status == "needs_interpretation"


def test_explicit_zero_wait_is_distinct_from_unknown(candidate):
    propose(candidate[0], "ped_waiting_period", "0", "days")
    value = field(build(candidate), "ped_waiting_period").value
    assert value.count == 0 and value.unit == "days"


def test_revision_date_never_becomes_active_policy_interval(candidate):
    propose(candidate[0], "effective_date", "2026-04-29", "date",
            conditions=["Product revision only"])
    value = field(build(candidate), "effective_date").value
    assert value.value == date(2026, 4, 29)
    assert value.meaning == "requires_applicability_review"
    preview = assess_draft(build(candidate).model_dump_json(), candidate[1], as_of=TODAY)
    assert any(b["code"] == "applicability_mapping_required" for b in preview["blockers"])


def test_reversed_age_bounds_are_an_explicit_blocker(candidate):
    propose(candidate[0], "adult_entry_age_min", "65", "years")
    propose(candidate[0], "adult_entry_age_max", "18", "years")
    preview = assess_draft(build(candidate).model_dump_json(), candidate[1], as_of=TODAY)
    assert any(b["code"] == "conflicting_age_bounds" for b in preview["blockers"])


@pytest.mark.parametrize("mutation", [
    "approval", "production", "status", "digest", "normalized_value", "duplicate_field",
    "strip_conditions", "future_date", "predate_sources", "extra_approval",
])
def test_tampered_or_self_approved_draft_is_rejected(candidate, mutation):
    propose(candidate[0], "ped_waiting_period", "36", "calendar_months",
            conditions=["Schedule selection required"])
    raw = json.loads(build(candidate).model_dump_json())
    if mutation == "approval":
        raw["approved_for_import"] = True
    elif mutation == "production":
        raw["production_approved"] = True
    elif mutation == "status":
        raw["review_status"] = "approved"
    elif mutation == "digest":
        raw["source_package_sha256"] = "0" * 64
    elif mutation == "normalized_value":
        next(f for f in raw["fields"] if f["name"] == "ped_waiting_period")["value"]["count"] = 0
    elif mutation == "duplicate_field":
        raw["fields"][0] = deepcopy(raw["fields"][1])
    elif mutation == "strip_conditions":
        for item in raw["source_package"]["fields"]:
            item["conditions"] = []
    elif mutation == "future_date":
        raw["normalized_on"] = "2027-01-01"
    elif mutation == "predate_sources":
        raw["normalized_on"] = "2026-10-01"
    else:
        raw["reviewer"] = "trusted-reviewer"
    with pytest.raises(ValueError):
        assess_draft(json.dumps(raw), candidate[1], as_of=TODAY)


def test_preview_rechecks_pdf_bytes_and_duplicate_json(candidate):
    raw = build(candidate).model_dump_json()
    with pytest.raises(ValueError, match="pinned hash"):
        assess_draft(raw, {"wording": candidate[1]["wording"] + b"changed"}, as_of=TODAY)
    with pytest.raises(ValueError, match="Duplicate JSON"):
        assess_draft(raw.replace('"approved_for_import":false',
                                 '"approved_for_import":true,"approved_for_import":false'),
                     candidate[1], as_of=TODAY)


def test_digest_is_stable_and_binds_evidence_conditions(candidate):
    propose(candidate[0], "uin", "SYNTHETIC-UIN", "text")
    first = assess_draft(build(candidate).model_dump_json(), candidate[1], as_of=TODAY)
    second = assess_draft(build(candidate).model_dump_json(), candidate[1], as_of=TODAY)
    assert first["draft_sha256"] == second["draft_sha256"]
    propose(candidate[0], "uin", "SYNTHETIC-UIN", "text", conditions=["Selected variant only"])
    changed = assess_draft(build(candidate).model_dump_json(), candidate[1], as_of=TODAY)
    assert changed["draft_sha256"] != first["draft_sha256"]


def test_empty_review_notes_cannot_bypass_approval_gate(candidate):
    propose(candidate[0], "uin", "SYNTHETIC-UIN", "text", notes=[])
    preview = assess_draft(build(candidate).model_dump_json(), candidate[1], as_of=TODAY)
    assert not preview["approved_for_import"]
    assert any(b["code"] == "authenticated_review_required" for b in preview["blockers"])
