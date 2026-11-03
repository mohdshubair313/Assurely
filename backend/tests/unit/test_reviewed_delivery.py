"""Fresh checks cannot be replaced by checkpoint flags or notification receipts."""

import copy
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.v1.message import build_delivery_response, build_message_response
from app.db.reviewed_delivery import check_reviewed_delivery
from app.graph.nodes.explanation_report import explanation_report_node
from app.main import app
from tests.unit.test_reviewed_report import state as _state

state = _state


@pytest.mark.asyncio
async def test_current_evidence_is_rechecked_each_time_without_authorizing_release(state):
    state.update(await explanation_report_node(state))
    original = copy.deepcopy(state)
    fresh = copy.deepcopy(state["draft_output"]["reviewed_comparison"])
    fresh["checked_at"] = datetime.now(UTC).isoformat()
    lookup = AsyncMock(return_value=fresh)
    with patch("app.db.reviewed_delivery.compare_terms", lookup):
        for _ in range(2):
            result = await check_reviewed_delivery(AsyncMock(), "https://issuer.test", state)
            assert result.evidence_current
            assert result.reason == "advisor_authorization_required"
    assert lookup.await_count == 2 and state == original


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["revoked", "event", "amount", "hash", "condition"])
async def test_fresh_lookup_mismatch_blocks_old_report(state, change):
    state.update(await explanation_report_node(state))
    fresh = copy.deepcopy(state["draft_output"]["reviewed_comparison"])
    cap = fresh["items"][0]["capabilities"][0]
    if change == "revoked":
        cap.update(status="unavailable", reason="revoked", facts=[])
    elif change == "event":
        cap["scope_review"]["verification_event_id"] = "00000000-0000-4000-8000-000000000099"
        cap["facts"][0]["verification_event_id"] = cap["scope_review"]["verification_event_id"]
    elif change == "amount":
        cap["facts"][0]["value"]["amounts"][0] += 1
    elif change == "hash":
        cap["facts"][0]["source"][0]["sha256"] = "c" * 64
    else:
        cap["conditions"]["any_of"][0][0]["value"] = 90
    with patch("app.db.reviewed_delivery.compare_terms", AsyncMock(return_value=fresh)):
        result = await check_reviewed_delivery(AsyncMock(), "https://issuer.test", state)
    assert not result.evidence_current


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["reply", "citation", "scenario", "status", "partial", "float"])
async def test_changed_or_incomplete_report_never_uses_old_approval(state, change):
    state.update(await explanation_report_node(state))
    state["output"] = copy.deepcopy(state["output"])
    if change == "reply":
        state["output"]["reply"] = "Altered report"
    elif change == "citation":
        state["output"]["sentences"][0]["citations"][0]["last_verified"] = "2000-01-01"
    elif change == "scenario":
        state["reviewed_comparison_request"] = copy.deepcopy(state["reviewed_comparison_request"])
        state["reviewed_comparison_request"]["items"][0]["context"]["entry_age_years"] = 90
    elif change == "status":
        state["output"]["report_status"] = "ready"
    elif change == "float":
        state["output"]["sentences"][0]["citations"][0]["value"]["amounts"][0] = 50_000_001.0
    else:
        state["output"]["reviewed_report"]["unavailable_capabilities"] = [{"reason": "expired"}]
    state.update(approved=True, delivery_hold=False, escalation=False)
    with patch("app.db.reviewed_delivery.compare_terms", AsyncMock()) as lookup:
        result = await check_reviewed_delivery(AsyncMock(), "https://issuer.test", state)
    assert not result.evidence_current
    lookup.assert_not_awaited()
    assert build_message_response("test", state).output == {}


@pytest.mark.asyncio
async def test_database_failure_is_redacted_and_snapshot_unchanged(state):
    state.update(await explanation_report_node(state))
    original = copy.deepcopy(state)
    with patch("app.api.v1.message.AsyncSessionLocal", side_effect=RuntimeError("private failure")):
        response = await build_delivery_response("test", state)
    assert response.delivery_hold and response.output == {} and state == original
    assert "private failure" not in response.model_dump_json()


@pytest.mark.asyncio
async def test_public_boundary_invokes_check_but_cannot_release_on_consistency_alone(state):
    state.update(await explanation_report_node(state))
    state.update(approved=True, delivery_hold=False, escalation=False)
    db = AsyncMock()
    db.__aenter__.return_value = db
    transaction = AsyncMock()
    db.begin = MagicMock(return_value=transaction)
    with (
        patch("app.api.v1.message.AsyncSessionLocal", return_value=db),
        patch("app.api.v1.message.check_reviewed_delivery", AsyncMock(return_value=
              SimpleNamespace(evidence_current=True, reason="advisor_authorization_required")))
        as gate,
    ):
        response = await build_delivery_response("test", state)
    gate.assert_awaited_once()
    assert response.delivery_hold and response.output == {}


@pytest.mark.asyncio
async def test_production_does_not_release_legacy_checkpoint(state):
    state.pop("reviewed_comparison_request")
    state["draft_output"] = {}
    state.update(approved=True, escalation=False, delivery_hold=False,
                 output={"report_status": "ready", "reply": "Legacy", "sentences": [{}]})
    with patch("app.api.v1.message.get_settings", return_value=SimpleNamespace(
        environment="production", auth_issuer="https://issuer.test",
    )):
        response = await build_delivery_response("test", state)
    assert response.delivery_hold and response.output == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["message", "session"])
async def test_actual_http_boundaries_call_fresh_check_and_redact(state, endpoint):
    state.update(await explanation_report_node(state))
    state["messages"] = [{"role": "assistant", "content": "PRIVATE_REPORT_SENTINEL"}]
    graph = SimpleNamespace(ainvoke=AsyncMock(return_value=state), aget_state=AsyncMock(
        return_value=None if endpoint == "message" else SimpleNamespace(values=state),
    ))
    db = AsyncMock()
    db.__aenter__.return_value = db
    db.get.return_value = None
    db.begin = MagicMock(return_value=AsyncMock())
    with (
        patch("app.api.v1.message._app_graph", graph),
        patch("app.api.v1.message.AsyncSessionLocal", return_value=db),
        patch("app.api.v1.sessions.AsyncSessionLocal", return_value=db),
        patch("app.api.v1.message.check_reviewed_delivery", AsyncMock(return_value=
              SimpleNamespace(evidence_current=False, reason="publication_or_evidence_changed")))
        as gate,
    ):
        client = TestClient(app)
        response = (client.post("/v1/message", json={"user_message": "Explain health cover"})
                    if endpoint == "message" else client.get("/v1/session/reviewed-report"))
    assert response.status_code == 200
    gate.assert_awaited_once()
    assert "PRIVATE_REPORT_SENTINEL" not in response.text
    assert "500000.01" not in response.text
