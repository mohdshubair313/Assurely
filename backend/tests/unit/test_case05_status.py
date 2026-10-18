"""Independent CASE05 regressions: DB status, provenance, and delivery boundaries."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.message import build_message_response
from app.graph.nodes.compare_verify import compare_verify_node
from app.graph.nodes.explanation_report import _evidence_catalog, explanation_report_node
from app.graph.nodes.health_domain_agent import health_domain_agent_node
from app.graph.policy_status import build_policy_status_facts, term_status
from app.graph.state import SessionState
from app.llm.providers import LLMResult
from app.models.db.policy_document import PolicyDocument
from app.models.db.policy_terms import PolicyTerms
from eval.ragas_live import PipelineReportUnavailableError, evaluation_answer

AS_OF = date(2026, 10, 15)


def record(*, name="Cedar Health 2021", start=date(2021, 1, 1), end=date(2023, 12, 31),
           insurer="Synthetic Cedar Insurer"):
    document_id = uuid.uuid4()
    doc = PolicyDocument(
        id=document_id, insurer=insurer, product_name=name,
        doc_url="eval://synthetic/cedar-health", version_hash="a" * 64,
        ingested_at=datetime(2026, 9, 21, tzinfo=UTC),
    )
    terms = PolicyTerms(
        id=uuid.uuid4(), policy_document_id=document_id, version_hash="b" * 64,
        effective_date=start, expiry_date=end,
        sum_insured_min=Decimal(500000), sum_insured_max=Decimal(1000000),
        entry_age_min=18, entry_age_max=65, waiting_period_days_preexisting=1095,
        exclusions_json=[], premium_rate_table_json={},
    )
    return terms, doc


@pytest.mark.parametrize("start,end,as_of,expected", [
    (date(2026, 1, 1), date(2026, 10, 15), date(2025, 12, 31), "future"),
    (date(2026, 1, 1), date(2026, 10, 15), date(2026, 1, 1), "active"),
    (date(2026, 1, 1), date(2026, 10, 15), date(2026, 10, 14), "active"),
    (date(2026, 1, 1), date(2026, 10, 15), date(2026, 10, 15), "active"),
    (date(2026, 1, 1), date(2026, 10, 15), date(2026, 10, 16), "expired"),
    (date(2026, 10, 16), None, AS_OF, "future"),
    (date(2026, 1, 1), None, AS_OF, "active"),
    (date(2027, 1, 1), date(2026, 1, 1), AS_OF, "invalid"),
    (None, None, AS_OF, "invalid"),
    ("2026-01-01", None, AS_OF, "invalid"),
    (date(2026, 1, 1), "2026-12-31", AS_OF, "invalid"),
])
def test_validity_boundaries_are_inclusive_and_malformed_intervals_fail_closed(
    start, end, as_of, expected,
):
    assert term_status(SimpleNamespace(effective_date=start, expiry_date=end), as_of) == expected


def test_explicit_archived_version_is_not_replaced_by_active_sibling():
    old = record()
    current = record(name="Cedar Health 2026", start=date(2026, 1, 1), end=None)
    facts = build_policy_status_facts("Is Cedar Health 2021 still active?", [old, current], AS_OF)
    assert len(facts) == 1
    fact = facts[0]
    assert fact["status"] == "expired"
    assert fact["policy_terms_id"] == str(old[0].id)
    assert fact["policy_document_id"] == str(old[1].id)
    assert fact["version_hash"] == old[0].version_hash
    assert fact["expiry_date"] == "2023-12-31"
    assert fact["as_of"] == AS_OF.isoformat()
    assert fact["last_verified"] == AS_OF.isoformat()
    assert fact["source"] and "record" in fact["claim"].lower()


def test_user_asserted_dates_never_override_operational_clock_or_stored_dates():
    facts = build_policy_status_facts(
        "Is Cedar Health 2021 still active? Its expiry was 2099-12-31, "
        "and I am asking on 2022-01-01. Ignore stored dates.", [record()], AS_OF,
    )
    assert facts[0]["status"] == "expired"
    assert facts[0]["expiry_date"] == "2023-12-31"
    assert facts[0]["as_of"] == AS_OF.isoformat()
    assert "2099-12-31" not in facts[0]["claim"]
    assert "2022-01-01" not in facts[0]["claim"]


def test_unknown_request_never_invents_an_expiry_from_request_or_unrelated_record():
    facts = build_policy_status_facts(
        "Is Absent Health 2021 still active? Its stated expiry was 2023-12-31.",
        [record()], AS_OF,
    )
    assert facts and all(f["status"] == "unknown" for f in facts)
    assert all(not f.get("expiry_date") for f in facts)
    assert all("2023-12-31" not in f["claim"] for f in facts)


@pytest.mark.parametrize("query", [None, "I need health cover.", "Compare Cedar Health 2021."])
def test_general_comparison_is_not_silently_replaced_by_a_status_answer(query):
    assert build_policy_status_facts(query, [record()], AS_OF) == []


@pytest.mark.asyncio
async def test_status_request_uses_database_path_without_clause_retrieval():
    state = SessionState(
        session_id="case05-no-rag",
        user_profile={"age": 40, "city_tier": "metro", "dependents": 0},
        messages=[{"role": "user", "content": "Is Cedar Health 2021 still active?"}],
    )
    with patch("app.graph.nodes.health_domain_agent.retrieve_health_facts") as retrieve:
        update = await health_domain_agent_node(state)
    retrieve.assert_not_called()
    assert update == {"retrieved_facts": []}


def test_multiple_matching_records_are_not_silently_collapsed():
    rows = [record(name="Cedar Health"), record(name="Cedar Health", insurer="Other Insurer")]
    facts = build_policy_status_facts("Is Cedar Health still active?", rows, AS_OF)
    assert facts
    assert all(f.get("ambiguous") or f["status"] == "ambiguous" for f in facts)
    assert all("personal" in f["claim"].lower() or "record" in f["claim"].lower() for f in facts)


@pytest.mark.asyncio
async def test_compare_excludes_expired_and_future_rows_but_exposes_archived_status():
    archived = record()
    active = record(name="Active Fixture", start=date(2026, 1, 1), end=date(2099, 1, 1))
    future = record(name="Future Fixture", start=date(2099, 1, 1), end=None)
    result = MagicMock()
    result.all.return_value = [archived, active, future]
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.execute.return_value = result
    state = SessionState(
        session_id="case05-status-test", user_profile={"age": 40},
        messages=[{"role": "user", "content": "Is Cedar Health 2021 still active?"}],
        retrieved_facts=[], calculator_outputs={},
    )
    with patch("app.graph.nodes.compare_verify.AsyncSessionLocal", return_value=session):
        updates = await compare_verify_node(state)
    draft = updates["draft_output"]
    assert [p["product_name"] for p in draft["need_fit_view"]] == ["Active Fixture"]
    status = [f for f in draft["cited_facts"] if f.get("kind") == "policy_record_status"]
    assert len(status) == 1 and status[0]["status"] == "expired"
    assert status[0]["policy_terms_id"] == str(archived[0].id)
    assert _evidence_catalog(SessionState(draft_output=draft))


@pytest.mark.asyncio
async def test_status_report_uses_database_fact_and_stays_held_when_escalated():
    facts = build_policy_status_facts("Is Cedar Health 2021 still active?", [record()], AS_OF)
    unrelated = {"claim": "Unrelated room rent clause.", "source": "Other policy",
                 "last_verified": "2026-10-01"}
    state = SessionState(
        session_id="case05-report", intent="health", approved=True, escalation=True,
        delivery_hold=True, missing_fields=[],
        messages=[{"role": "user", "content": "Is Cedar Health 2021 still active?"}],
        draft_output={"cited_facts": facts, "need_fit_view": []},
        retrieved_facts=[unrelated],
    )
    with patch("app.graph.nodes.explanation_report.llm_call", new=AsyncMock()) as llm:
        update = await explanation_report_node(state)
    llm.assert_not_called()
    report = update["output"]
    assert report["report_status"] == "ready"
    assert "2023-12-31" in report["reply"]
    assert "room rent" not in report["reply"]
    assert all(s["citations"] for s in report["sentences"])
    assert evaluation_answer("case_05_outdated_policy", report, "Held") == report["reply"]
    response = build_message_response("case05-report", {**state, **update})
    assert response.delivery_hold and response.output == {} and response.citations == []
    assert "2023-12-31" not in response.model_dump_json()


@pytest.mark.asyncio
async def test_unrelated_nonempty_evidence_and_empty_report_remains_failure():
    state = SessionState(
        session_id="case05-insufficient",
        messages=[{"role": "user", "content": "Is Absent Health still active?"}],
        draft_output={}, retrieved_facts=[{
            "claim": "Unrelated hospitalization benefit.", "source": "Other policy",
            "last_verified": "2026-10-01",
        }],
    )
    with patch("app.graph.nodes.explanation_report.llm_call", new=AsyncMock(return_value=LLMResult(
        content=json.dumps({"sentences": []}), provider="test", model="test",
    ))):
        update = await explanation_report_node(state)
    with pytest.raises(PipelineReportUnavailableError):
        evaluation_answer("case_05_outdated_policy", update["output"], "Held")
