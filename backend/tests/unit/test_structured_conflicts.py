"""Structured contradictions must fail closed without conflating document identities."""

import json
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.message import build_message_response
from app.graph.nodes.compare_verify import compare_verify_node
from app.graph.nodes.escalate import escalate_node
from app.graph.nodes.explanation_report import explanation_report_node
from app.graph.nodes.guardrail import guardrail_node
from app.graph.nodes.persist_memory import persist_memory_node
from app.graph.state import create_initial_state
from app.graph.structured_conflicts import detect_structured_conflicts
from app.llm.providers import LLMResult
from app.models.db.policy_document import PolicyDocument
from app.models.db.policy_terms import PolicyTerms

AS_OF = date(2026, 10, 21)


def record(doc=None, **changes):
    doc = doc or PolicyDocument(id=uuid.uuid4(), insurer="Synthetic insurer",
        product_name="Synthetic cover", version_hash="document-v1", doc_url="eval://fixture")
    values = dict(id=uuid.uuid4(), policy_document_id=doc.id, version_hash="terms-v1",
        effective_date=date(2026, 1, 1), expiry_date=None,
        sum_insured_min=Decimal("500000.00"), sum_insured_max=Decimal("1000000.00"),
        entry_age_min=18, entry_age_max=65, waiting_period_days_preexisting=1095,
        exclusions_json=[], premium_rate_table_json={"base_10L": {"age_18_35": 10000}})
    values.update(changes)
    return PolicyTerms(**values), doc


@pytest.mark.parametrize("field,value", [
    ("sum_insured_min", Decimal("500000.01")), ("sum_insured_max", Decimal("2000000")),
    ("entry_age_min", 21), ("entry_age_max", 70), ("waiting_period_days_preexisting", 730),
    ("exclusions_json", ["Cosmetic treatment"]),
    ("premium_rate_table_json", {"base_10L": {"age_18_35": 10001}}),
])
def test_conflicts_preserve_values_and_provenance_in_stable_order(field, value):
    first = record()
    second = record(first[1], **{field: value, "version_hash": "terms-v2"})
    conflicts = detect_structured_conflicts([first, second], AS_OF)
    assert len(conflicts) == 1
    assert conflicts == detect_structured_conflicts([second, first], AS_OF)
    conflict = conflicts[0]
    assert conflict["field"].startswith(field)
    assert conflict["policy_document_id"] == str(first[1].id)
    assert {item["policy_terms_id"] for item in conflict["evidence"]} == {
        str(first[0].id), str(second[0].id)}
    assert {item["terms_version_hash"] for item in conflict["evidence"]} == {
        "terms-v1", "terms-v2"}
    assert all(item["last_verified"] == AS_OF.isoformat() and item["source"]
               and item["verification_scope"] == "database_record_lookup"
               for item in conflict["evidence"])
    if field == "sum_insured_min":
        assert {item["value"] for item in conflict["evidence"]} == {"500000", "500000.01"}


def test_normalization_missing_values_and_disjoint_rate_keys_are_not_conflicts():
    first = record(exclusions_json=["Cosmetic  Treatment", "Dental"])
    second = record(first[1], sum_insured_min=None,
        exclusions_json=["dental", " cosmetic treatment "],
        premium_rate_table_json={"base_10L": {"age_36_45": 12000}})
    assert detect_structured_conflicts([first, second], AS_OF) == []


def test_same_product_name_in_different_documents_is_not_conflated():
    assert detect_structured_conflicts([record(), record(entry_age_max=70)], AS_OF) == []


@pytest.mark.parametrize("start,end,expected", [
    (date(2026, 1, 1), date(2026, 10, 20), False),
    (date(2026, 10, 22), None, False),
    (date(2027, 1, 1), date(2026, 1, 1), False),
    (AS_OF, None, True), (date(2026, 1, 1), AS_OF, True),
])
def test_only_concurrent_active_windows_conflict(start, end, expected):
    first = record()
    second = record(first[1], effective_date=start, expiry_date=end, entry_age_max=70)
    assert bool(detect_structured_conflicts([first, second], AS_OF)) is expected


async def compare(rows):
    state = create_initial_state("structured-conflicts", "Explain health cover")
    state["user_profile"] = {"age": 30, "city_tier": "tier_1", "dependents": 0,
                             "pre_existing_conditions": False}
    db = AsyncMock()
    db.__aenter__.return_value = db
    db.execute.return_value = MagicMock()
    db.execute.return_value.all.return_value = rows
    with patch("app.graph.nodes.compare_verify.AsyncSessionLocal", return_value=db):
        state.update(await compare_verify_node(state))
    return state


@pytest.mark.asyncio
async def test_conflict_generates_report_but_holds_delivery_even_with_score_one():
    first = record()
    state = await compare([first, record(first[1], entry_age_max=70)])
    assert state["draft_output"]["need_fit_view"] == []
    assert state["draft_output"]["evidence_conflicts"]
    with patch("app.graph.nodes.guardrail.calculate_confidence_score", return_value=1.0):
        state.update(await guardrail_node(state))
    assert state["approved"] is False and state["escalation"] is True
    assert "Conflicting active policy records" in state["escalation_reason"]
    with patch("app.graph.nodes.explanation_report.llm_call", new=AsyncMock(return_value=LLMResult(
        content=json.dumps({"sentences": [{"text": "Conflicting records require review.",
                                           "evidence_ids": ["E1"]}]}),
        provider="test", model="test",
    ))):
        state.update(await explanation_report_node(state))
    assert state["output"]["report_status"] == "ready"
    with patch("app.graph.nodes.escalate.dispatch_notification", new=AsyncMock(
        return_value={"status": "unconfigured"})):
        state.update(await escalate_node(state))
    assert state["delivery_hold"] is True
    response = build_message_response(state["session_id"], state)
    assert response.output == {} and response.citations == [] and response.delivery_hold
    assert str(first[1].id) not in response.model_dump_json()
    state["user_id"] = str(uuid.uuid4())
    db = AsyncMock()
    db.__aenter__.return_value = db
    db.add = MagicMock()
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalar_one.return_value = uuid.UUID(state["user_id"])
    with patch("app.graph.nodes.persist_memory.AsyncSessionLocal", return_value=db):
        await persist_memory_node(state)
    assert db.add.call_args.args[0].rules_engine_output_json["evidence_conflicts"] == (
        state["draft_output"]["evidence_conflicts"])


@pytest.mark.asyncio
async def test_consistent_control_remains_approved_and_deliverable():
    first = record()
    state = await compare([first, record(first[1])])
    assert not state["draft_output"]["evidence_conflicts"]
    assert len(state["draft_output"]["need_fit_view"]) == 2
    state.update(await guardrail_node(state))
    assert state["approved"] is True and state["escalation"] is False
    assert (await escalate_node(state))["delivery_hold"] is False


@pytest.mark.asyncio
async def test_conflict_suppresses_only_affected_document_but_holds_entire_turn():
    first = record()
    unaffected = record()
    state = await compare([first, record(first[1], entry_age_max=70), unaffected])
    assert [item["policy_document_id"] for item in state["draft_output"]["need_fit_view"]] == [
        str(unaffected[1].id)]
    state.update(await guardrail_node(state))
    assert state["approved"] is False and state["escalation"] is True
