"""Scoped approval is independent of model scores, advisor decisions and delivery."""

import copy
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.message import build_message_response
from app.graph.nodes.explanation_report import explanation_report_node
from app.graph.nodes.guardrail import guardrail_node
from tests.unit.test_reviewed_report import capability
from tests.unit.test_reviewed_report import state as _state

state = _state


@pytest.fixture
def boundary(state):
    fresh = copy.deepcopy(state["draft_output"]["reviewed_comparison"])
    fresh["checked_at"] = datetime.now(UTC).isoformat()
    lookup = AsyncMock(return_value=fresh)
    factory = MagicMock()
    factory.return_value.__aenter__.return_value.begin = MagicMock()
    with (
        patch("app.graph.nodes.guardrail.get_settings", return_value=SimpleNamespace(
            environment="production", auth_issuer="https://issuer.test")),
        patch("app.graph.reviewed_guardrail.AsyncSessionLocal", factory),
        patch("app.graph.reviewed_guardrail.compare_terms", lookup),
    ):
        yield lookup


@pytest.mark.asyncio
async def test_current_scoped_facts_approve_without_output_or_delivery_authority(state, boundary):
    original = copy.deepcopy(state)
    for _ in range(2):
        result = await guardrail_node(state)
        assert result["approved"] is True and result["escalation"] is True
        assert "output" not in result and "delivery_hold" not in result
        assert result["confidence_score"] == 0.0
        assert result["confidence_inputs"]["confidence_available"] is False
    assert state == original and boundary.await_count == 2
    state.update(result)
    state.update(await explanation_report_node(state))
    assert state["output"]["report_status"] == "reviewed_report_held"
    response = build_message_response("test", state)
    assert response.delivery_hold and response.output == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    "revoked", "amount", "float", "source", "event", "expiry", "scope", "option",
])
async def test_current_lookup_changes_never_inherit_approval(state, boundary, change):
    fresh = boundary.return_value
    cap = fresh["items"][0]["capabilities"][0]
    fact = cap["facts"][0]
    if change == "revoked":
        cap.update(status="unavailable", reason="revoked", facts=[])
    elif change == "amount":
        fact["value"]["amounts"][0] += 1
    elif change == "float":
        fact["value"]["amounts"][0] = float(fact["value"]["amounts"][0])
    elif change == "source":
        fact["source"][0]["sha256"] = "c" * 64
    elif change == "event":
        event = "00000000-0000-4000-8000-000000000099"
        cap["scope_review"]["verification_event_id"] = event
        fact["verification_event_id"] = event
    elif change == "expiry":
        cap["expires_at"] = "2000-01-01T00:00:00Z"
    elif change == "scope":
        cap["conditions"]["any_of"][0][0]["value"] = 30
    else:
        cap["applicability"]["selected_options"] = ["optional"]
    state.update(approved=True, escalation=False, confidence_score=1.0)
    result = await guardrail_node(state)
    assert result["approved"] is False and result["escalation"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    "missing_request", "rejected", "pending", "missing_fields", "partial", "legacy",
    "conflict", "hidden", "unknown_field", "missing_source", "unknown_condition",
    "unreviewed_scope", "wrong_scenario", "prohibited", "future_lookup",
])
async def test_invalid_or_mixed_snapshots_fail_closed(state, boundary, change):
    draft = state["draft_output"]
    cap = capability(state)
    if change == "missing_request":
        state.pop("reviewed_comparison_request")
    elif change in {"rejected", "pending"}:
        state["input_status"] = change
    elif change == "missing_fields":
        state["missing_fields"] = ["age"]
    elif change == "partial":
        draft["reviewed_comparison"]["status"] = "partial"
    elif change == "legacy":
        draft["need_fit_view"] = [{"eligible": True}]
    elif change == "conflict":
        draft["evidence_conflicts"] = [{"conflict": True}]
    elif change == "hidden":
        state["hidden_clauses"] = [{"claim": "Unreviewed clause"}]
    elif change == "unknown_field":
        draft["premium_estimate"] = 100
    elif change == "missing_source":
        cap["facts"][0]["source"] = []
    elif change == "unknown_condition":
        cap["conditions"] = {"any_of": [[{"field": "zone", "op": "eq", "value": "A"}]]}
    elif change == "unreviewed_scope":
        cap["storage_scope"] = "legacy"
    elif change == "wrong_scenario":
        state["reviewed_comparison_request"]["items"][0]["context"]["entry_age_years"] = 40
    elif change == "future_lookup":
        draft["reviewed_comparison"]["checked_at"] = "2999-01-01T00:00:00Z"
    else:
        cap["identity"][1] = "guaranteed approval"
        boundary.return_value = copy.deepcopy(draft["reviewed_comparison"])
    result = await guardrail_node(state)
    assert result["approved"] is False and result["escalation"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [RuntimeError("private db detail"), TimeoutError()])
async def test_failure_is_sanitized_and_overwrites_old_authority(state, boundary, failure):
    boundary.side_effect = failure
    result = await guardrail_node({**state, "approved": True})
    assert result["approved"] is False and result["escalation"] is True
    assert "private db detail" not in str(result)


@pytest.mark.asyncio
async def test_production_legacy_and_missing_issuer_fail_closed(state, boundary):
    state["draft_output"] = {"need_fit_view": []}
    state.pop("reviewed_comparison_request")
    result = await guardrail_node(state)
    assert result["approved"] is False
    boundary.assert_not_awaited()


@pytest.mark.asyncio
async def test_unconfigured_issuer_cannot_use_reviewed_snapshot(state, boundary):
    with patch("app.graph.nodes.guardrail.get_settings", return_value=SimpleNamespace(
        environment="production", auth_issuer="")):
        result = await guardrail_node(state)
    assert result["approved"] is False
    boundary.assert_not_awaited()
