"""The expired record is explicit synthetic eval data, never a production seed."""

import json
from datetime import date

import pytest

from app.db.seed import SEED_POLICIES
from eval.case05_fixture import (
    CASE_ID,
    FIXTURE_PATH,
    fixture_records,
    isolated_database_url,
    validate_database_name,
)

DATABASE = "insurance_case05_eval_012345abcdef"


@pytest.mark.parametrize("name", ["insurance", "postgres", "insurance_case05_eval_",
                                   "insurance_case05_eval_012345abcdef;DROP DATABASE insurance",
                                   "insurance_case05_eval_012345abcdef\n"])
def test_fixture_rejects_main_database_and_unsafe_or_ambiguous_identifiers(name):
    with pytest.raises(ValueError):
        validate_database_name(name)


def test_isolation_changes_database_only_and_retains_credentials_in_memory():
    assert isolated_database_url(
        "postgresql+asyncpg://user:synthetic-secret@postgres:5432/insurance", DATABASE, [CASE_ID],
    ) == f"postgresql+asyncpg://user:synthetic-secret@postgres:5432/{DATABASE}"


@pytest.mark.parametrize(
    "cases",
    [[], [CASE_ID, "case_01_normal_health"], ["case_01_normal_health"]],
)
def test_fixture_cannot_be_used_for_a_different_eval_scope(cases):
    with pytest.raises(ValueError):
        isolated_database_url("postgresql+asyncpg://u:p@postgres/insurance", DATABASE, cases)


def test_fixture_matches_original_case_and_has_no_invented_coverage_values():
    document, terms, provenance = fixture_records()
    case = json.loads((FIXTURE_PATH.parents[1] / "cases" / f"{CASE_ID}.json").read_text())
    assert str(document["id"]) == case["input"]["policy_document_id"]
    assert document["product_name"] == case["input"]["product_name"]
    assert terms["expiry_date"] == date.fromisoformat(case["input"]["expiry_date"])
    assert "synthetic" in document["insurer"].lower()
    assert document["doc_url"].startswith("eval://synthetic/")
    assert provenance["kind"] == "synthetic_isolated_evaluation_only"
    assert not any(field in terms for field in ("sum_insured_min", "entry_age_min",
                                               "waiting_period_days_preexisting"))
    assert not any(p["product_name"] == document["product_name"] for p in SEED_POLICIES)
