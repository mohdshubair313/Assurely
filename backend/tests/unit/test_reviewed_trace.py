"""Historical reviewed comparisons retain scoped evidence without delivery authority."""

import copy
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.graph.nodes.persist_memory import _reviewed_provenance, persist_memory_node
from app.graph.state import SessionState


def reviewed_state() -> SessionState:
    ref = {"source_id": "wording", "pdf_page": 7, "clause": "4.2", "quote": "12 months",
           "url": "https://example.org/policy.pdf", "sha256": "a" * 64,
           "unexpected": "must not persist"}
    cap = {
        "capability": "base_ped_wait", "status": "available", "policy_terms_id": "terms-1",
        "storage_scope": "reviewed_policy_terms", "expires_at": "2026-12-01T00:00:00Z",
        "scope_review": {"last_verified": "2026-11-01", "verification_event_id": "event-1",
                         "applicability_evidence": [{**ref, "pdf_page": 2}],
                         "condition_evidence": [{**ref, "pdf_page": 3}],
                         "identity_note_mappings": [], "condition_note_mappings": []},
        "facts": [{"name": "ped_waiting_period", "value": {"kind": "duration",
                   "unit": "calendar_months", "amount": 12}, "source": [ref],
                   "last_verified": "2026-11-01", "verification_event_id": "event-1",
                   "policy_terms_id": "terms-1"}],
    }
    return {
        "intent": "health", "missing_fields": [],
        "session_id": "reviewed-trace", "user_id": "00000000-0000-4000-8000-000000000123",
        "draft_output": {"stage": "compare_verify", "reviewed_comparison": {
            "scope": "reviewed_graph_comparison", "status": "partial",
            "checked_at": "2026-11-02T00:00:00Z", "customer_delivery_authorized": True,
            "items": [{"publication_digest": "b" * 64,
                       "scenario": {"residency": "private-residency", "entry_age_years": 41},
                       "capabilities": [cap, {**cap, "status": "unavailable",
                                              "reason": "revoked"}]},
                      {"publication_digest": "c" * 64, "capabilities": [copy.deepcopy(cap)]}],
        }},
    }


def test_scoped_trace_preserves_units_and_evidence_without_scenario_or_authority() -> None:
    state = reviewed_state()
    original = copy.deepcopy(state)
    audit, versions, sources = _reviewed_provenance(state)
    assert state == original
    assert audit is not None
    assert audit["customer_delivery_authorized"] is False
    assert audit["requires_fresh_lookup"] is True
    assert len(versions) == len(sources) == 2
    assert {v["publication_digest"] for v in versions} == {"b" * 64, "c" * 64}
    available, unavailable = audit["items"][0]["capabilities"]
    assert unavailable["reason"] == "revoked" and unavailable["facts"] == []
    assert "scope_review" not in unavailable
    fact = available["facts"][0]
    assert fact["value"]["unit"] == "calendar_months"
    assert fact["last_verified"] == "2026-11-01"
    assert fact["provenance_complete"] is True
    assert available["scope_review"]["applicability_evidence"][0]["pdf_page"] == 2
    assert available["scope_review"]["condition_evidence"][0]["pdf_page"] == 3
    serialized = json.dumps((audit, versions, sources))
    assert "private-residency" not in serialized
    assert "entry_age_years" not in serialized
    assert "must not persist" not in serialized


@pytest.mark.parametrize("missing", ["source", "verification_event_id", "policy_terms_id"])
def test_missing_source_is_recorded_as_incomplete_not_invented(missing: str) -> None:
    state = reviewed_state()
    cap = state["draft_output"]["reviewed_comparison"]["items"][0]["capabilities"][0]
    del cap["facts"][0][missing]
    audit, _, _ = _reviewed_provenance(state)
    assert audit is not None
    fact = audit["items"][0]["capabilities"][0]["facts"][0]
    assert fact["provenance_complete"] is False
    if missing == "source":
        assert fact["source"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("rejected", [False, True])
async def test_node_writes_reviewed_evidence_only_for_current_accepted_turn(rejected: bool) -> None:
    state = reviewed_state()
    if rejected:
        state["input_status"] = "rejected"
    db = AsyncMock()
    db.__aenter__.return_value = db
    db.add = MagicMock()
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalar_one.return_value = uuid.UUID(state["user_id"])
    with patch("app.graph.nodes.persist_memory.AsyncSessionLocal", return_value=db):
        result = await persist_memory_node(state)
    trace = db.add.call_args.args[0]
    assert bool(trace.policy_versions_evaluated_json) is not rejected
    assert bool(trace.sources_per_claim_json) is not rejected
    assert bool(trace.rules_engine_output_json["reviewed_comparison"]) is not rejected
    assert result == {"decision_trace_persisted": True, "profile_memory_persisted": False}
    db.commit.assert_awaited_once()


@pytest.mark.parametrize("scope", ["internal_review_preview", None])
def test_operator_preview_is_not_attributed_to_graph(scope: str | None) -> None:
    state = reviewed_state()
    state["draft_output"]["reviewed_comparison"]["scope"] = scope
    assert _reviewed_provenance(state) == (None, [], {})


@pytest.mark.parametrize("updates", [
    {"missing_fields": ["age"]}, {"intent": "life"}, {"intent": "unclear"},
])
def test_early_exit_turn_does_not_reuse_previous_reviewed_comparison(updates: dict) -> None:
    state = reviewed_state()
    state.update(updates)
    assert _reviewed_provenance(state) == (None, [], {})
