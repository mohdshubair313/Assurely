"""Scoped report rendering and fail-closed delivery from synthetic reviewed facts."""

import copy
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.message import build_message_response
from app.graph.nodes.explanation_report import explanation_report_node


@pytest.fixture
def state():
    now = datetime.now(UTC)
    day = now.date().isoformat()
    ref = {"source_id": "wording", "pdf_page": 7, "clause": "4.2", "quote": "Synthetic fact",
           "url": "https://example.org/policy.pdf", "sha256": "a" * 64}
    context = {"transaction": "issue", "transaction_date": day, "cover_basis": "individual",
               "selected_options": [], "entry_age_years": 35}
    terms = "00000000-0000-4000-8000-000000000001"
    event = "00000000-0000-4000-8000-000000000002"
    fact = {"name": "sum_insured_options", "value": {
        "kind": "cover_options", "currency": "INR", "unit": "paise",
        "amounts": [50_000_001, 100_000_000], "interpolation": "not_authorized",
    }, "policy_terms_id": terms, "verification_event_id": event,
        "last_verified": day, "source": [ref]}
    cap = {"capability": "coverage_options", "status": "available",
           "publication_digest": "b" * 64, "policy_terms_id": terms,
           "storage_scope": "reviewed_policy_terms",
           "verification_scope": "human_reviewed_conditional_product_facts",
           "expires_at": (now + timedelta(days=1)).isoformat(),
           "identity": ["Synthetic Insurer", "Health Plan", "SYNTH-UIN", "Base"],
           "facts": [fact], "conditions": {"any_of": [[{
               "field": "entry_age_years", "op": "gte", "value": 18,
           }]]}, "applicability": {
               "date_basis": "policy_issue_date", "window": {"start": day,
                   "end_kind": "no_declared_end", "end": None}, "cover_basis": "individual",
               "selected_options": [], "rationale": "Synthetic scope",
               "evidence": [{k: ref[k] for k in ("source_id", "pdf_page", "clause", "quote")}],
           }, "scope_review": {"last_verified": day, "verification_event_id": event,
               "applicability_evidence": [ref], "condition_evidence": [ref],
               "identity_note_mappings": [], "condition_note_mappings": []}}
    return {"intent": "health", "input_status": "accepted", "missing_fields": [],
            "session_id": "reviewed-report", "approved": False, "escalation": True,
            "delivery_hold": True, "reviewed_comparison_request": {"items": [{
                "publication_digest": "b" * 64, "capabilities": ["coverage_options"],
                "context": context}]}, "draft_output": {"stage": "compare_verify",
                "publication_gate": "blocked", "reviewed_comparison": {
                    "scope": "reviewed_graph_comparison", "status": "complete",
                    "checked_at": now.isoformat(), "requires_fresh_lookup": True,
                    "customer_delivery_authorized": False, "items": [{
                        "publication_digest": "b" * 64, "scenario": context,
                        "capabilities": [cap]}]}}}


def capability(state):
    return state["draft_output"]["reviewed_comparison"]["items"][0]["capabilities"][0]


@pytest.mark.asyncio
async def test_report_is_exact_scoped_sourced_and_held_even_with_spurious_release_flags(state):
    original = copy.deepcopy(state)
    with patch("app.graph.nodes.explanation_report.llm_call", new=AsyncMock()) as model:
        result = await explanation_report_node(state)
    model.assert_not_awaited()
    assert state == original and set(result) == {"output"}
    report = result["output"]
    assert report["report_status"] == "reviewed_report_held"
    assert report["claim_support"]["supported"] is True
    assert "INR 500000.01, INR 1000000.00" in report["reply"]
    assert "entry age years >= 18" in report["reply"]
    assert "policy issue date" in report["reply"]
    citation = report["sentences"][0]["citations"][0]
    assert citation["references"][0]["pdf_page"] == 7
    assert citation["condition_evidence"] and citation["applicability_evidence"]
    assert (citation["verification_event_id"]
            == capability(state)["scope_review"]["verification_event_id"])
    response = build_message_response("held", {
        **state, **result, "approved": True, "escalation": False, "delivery_hold": False,
    })
    assert response.delivery_hold and response.output == {} and response.draft_output == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("unit", ["days", "calendar_months"])
async def test_wait_units_are_not_converted(state, unit):
    cap = capability(state)
    cap["capability"] = "base_ped_wait"
    state["reviewed_comparison_request"]["items"][0]["capabilities"] = ["base_ped_wait"]
    cap["facts"][0].update(name="ped_waiting_period", value={
        "kind": "waiting_period", "count": 36, "unit": unit,
    })
    output = (await explanation_report_node(state))["output"]
    assert f"36 {unit.replace('_', ' ')}" in output["reply"]
    assert output["claim_support"]["supported"] is True


@pytest.mark.asyncio
async def test_unbounded_age_keeps_reviewed_basis_and_does_not_infer_eligibility(state):
    cap = capability(state)
    cap["capability"] = "adult_entry_ages"
    state["reviewed_comparison_request"]["items"][0]["capabilities"] = ["adult_entry_ages"]
    base = cap["facts"][0]
    cap["facts"] = [{**base, "name": name, "value": {"kind": "age", "years": years,
        "bound": "unbounded" if years is None else "finite",
        "age_basis": "nearest_birthday_at_entry"}} for name, years in (
            ("adult_entry_age_min", 18), ("adult_entry_age_max", None))]
    output = (await explanation_report_node(state))["output"]
    assert "no declared upper limit" in output["reply"]
    assert "nearest birthday at entry" in output["reply"]
    assert len(output["sentences"]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    "missing_source", "missing_scope_source", "wrong_event", "wrong_terms", "wrong_digest",
    "expired", "unknown_conditions", "unmet_conditions", "wrong_date_basis", "wrong_options",
    "unknown_end", "unreviewed_age", "bool_amount", "duplicate_fact", "missing_request",
    "wrong_scenario", "rejected", "prohibited_label",
])
async def test_invalid_snapshot_never_falls_back_to_legacy_or_model(state, change):
    cap = capability(state)
    fact = cap["facts"][0]
    if change == "missing_source":
        fact["source"] = []
    elif change == "missing_scope_source":
        cap["scope_review"]["condition_evidence"] = []
    elif change == "wrong_event":
        fact["verification_event_id"] = "00000000-0000-4000-8000-000000000009"
    elif change == "wrong_terms":
        fact["policy_terms_id"] = "wrong"
    elif change == "wrong_digest":
        cap["publication_digest"] = "c" * 64
    elif change == "expired":
        cap["expires_at"] = "2000-01-01T00:00:00Z"
    elif change in {"unknown_conditions", "unmet_conditions"}:
        cap["conditions"] = {"any_of": [[{"field": "entry_age_years" if change ==
            "unmet_conditions" else "zone", "op": "eq", "value": 99 if change ==
            "unmet_conditions" else "A"}]]}
    elif change == "wrong_date_basis":
        cap["applicability"]["date_basis"] = "policy_renewal_date"
    elif change == "wrong_options":
        cap["applicability"]["selected_options"] = ["optional cover"]
    elif change == "unknown_end":
        cap["applicability"]["window"]["end_kind"] = "unknown"
    elif change == "unreviewed_age":
        fact["value"] = {"kind": "age", "years": 18, "age_basis": "requires_rule_review"}
    elif change == "bool_amount":
        fact["value"]["amounts"] = [True]
    elif change == "duplicate_fact":
        cap["facts"].append(copy.deepcopy(fact))
    elif change == "missing_request":
        state.pop("reviewed_comparison_request")
    elif change == "wrong_scenario":
        item = state["draft_output"]["reviewed_comparison"]["items"][0]
        item["scenario"] = {**item["scenario"], "entry_age_years": 60}
    elif change == "rejected":
        state["input_status"] = "rejected"
    else:
        cap["identity"][1] = "Best Plan"
    state["retrieved_facts"] = [{"claim": "Fallback fact", "source": "RAG",
                                 "last_verified": "2026-01-01"}]
    with patch("app.graph.nodes.explanation_report.llm_call", new=AsyncMock()) as model:
        output = (await explanation_report_node(state))["output"]
    model.assert_not_awaited()
    assert not output.get("sentences") and not output.get("reply")


@pytest.mark.asyncio
async def test_unavailable_capabilities_remain_operational_metadata_without_facts(state):
    cap = capability(state)
    cap.update(status="unavailable", reason="revoked", facts=[])
    output = (await explanation_report_node(state))["output"]
    assert output["sentences"] == [] and output["reply"] == ""
    assert output["reviewed_report"]["unavailable_capabilities"][0]["reason"] == "revoked"


@pytest.mark.asyncio
async def test_partial_report_preserves_boolean_scope_and_review_note_evidence(state):
    cap = capability(state)
    cap["conditions"] = {"any_of": [
        [{"field": "entry_age_years", "op": "gte", "value": 18},
         {"field": "entry_age_years", "op": "lte", "value": 60}],
        [{"field": "zone", "op": "eq", "value": "A"}],
    ]}
    cap["scope_review"]["condition_note_mappings"] = [{
        "note_sha256": "d" * 64, "disposition": "condition", "rationale": "Age or zone scope",
        "evidence": copy.deepcopy(cap["scope_review"]["condition_evidence"]),
    }]
    item = state["draft_output"]["reviewed_comparison"]["items"][0]
    item["capabilities"].append({"capability": "base_ped_wait", "status": "unavailable",
                                 "reason": "capability_not_published", "facts": []})
    state["reviewed_comparison_request"]["items"][0]["capabilities"].append("base_ped_wait")
    output = (await explanation_report_node(state))["output"]
    assert len(output["sentences"]) == 1
    assert '(entry age years >= 18 AND entry age years <= 60) OR (zone = "A")' in output["reply"]
    citation = output["sentences"][0]["citations"][0]
    assert citation["condition_note_mappings"][0]["note_sha256"] == "d" * 64
    assert output["reviewed_report"]["unavailable_capabilities"][0]["capability"] == "base_ped_wait"
    assert "waiting period" not in output["reply"]
