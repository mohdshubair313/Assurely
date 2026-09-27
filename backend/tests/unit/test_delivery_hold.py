"""Public API must never expose held graph content through alternative fields."""

from copy import deepcopy
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.v1.message import build_message_response
from app.graph.build_graph import build_graph
from app.main import app


def completed_state() -> dict[str, Any]:
    sentinel = "WITHHELD_SYNTHETIC_DETAIL"
    return {
        "session_id": "delivery-test",
        "intent": "health",
        "approved": True,
        "escalation": False,
        "delivery_hold": False,
        "missing_fields": [],
        "advisor_notification": {},
        "output": {
            "reply": sentinel,
            "sentences": [{"text": sentinel, "citations": []}],
            "report_status": "ready",
        },
        "draft_output": {"claim": sentinel},
        "calculator_outputs": {"value": sentinel},
        "retrieved_facts": [{"claim": sentinel}],
        "hidden_clauses": [{"clause": sentinel}],
        "transparency_scores": {sentinel: 100},
        "guardrail_notes": [sentinel],
        "escalation_reason": sentinel,
        "messages": [{"role": "assistant", "content": sentinel}],
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"delivery_hold": True},
        {"escalation": True},
        {"approved": False},
        {"advisor_notification": {"status": "queued"}},
        {"advisor_notification": {"status": "failed"}},
        {"advisor_notification": {"status": "unconfigured"}},
    ],
)
def test_any_hold_condition_redacts_every_public_content_field(overrides: dict[str, Any]) -> None:
    state = {**completed_state(), **overrides}
    original = deepcopy(state)
    result = build_message_response("delivery-test", state)
    assert result.delivery_hold is True
    assert "WITHHELD_SYNTHETIC_DETAIL" not in result.model_dump_json()
    assert result.output == {} and result.citations == []
    assert result.draft_output == {} and result.calculator_outputs == {}
    assert result.hidden_clauses == [] and result.transparency_scores == {}
    assert result.guardrail_notes == []
    assert state == original  # Content remains available internally for advisor review.


@pytest.mark.parametrize("missing_key", ["delivery_hold", "approved"])
def test_missing_gate_fields_fail_closed(missing_key: str) -> None:
    state = completed_state()
    state.pop(missing_key)
    result = build_message_response("delivery-test", state)
    assert result.delivery_hold is True and result.output == {}


def test_only_approved_unheld_output_is_forwarded_without_mutation() -> None:
    state = completed_state()
    original = deepcopy(state)
    response = build_message_response("delivery-test", state)
    assert response.output == state["output"]
    assert response.reply == state["output"]["reply"]
    assert response.delivery_hold is False
    assert state == original


def test_intake_question_can_be_returned_without_held_content() -> None:
    state = {**completed_state(), "missing_fields": ["age"], "delivery_hold": True}
    result = build_message_response("delivery-test", state)
    assert result.reply == "Could you please share your age?"
    assert "WITHHELD_SYNTHETIC_DETAIL" not in result.model_dump_json()


def test_api_checks_hold_on_actual_response_path() -> None:
    state = {
        **completed_state(),
        "delivery_hold": True,
        "advisor_notification": {"status": "queued"},
    }
    graph = SimpleNamespace(
        aget_state=AsyncMock(return_value=None), ainvoke=AsyncMock(return_value=state)
    )
    with patch("app.api.v1.message._app_graph", graph):
        response = TestClient(app).post(
            "/v1/message", json={"session_id": "held", "user_message": "Hello"}
        )
    assert response.status_code == 200
    assert response.json()["delivery_hold"] is True
    assert response.json()["notification_status"] == "queued"
    assert "WITHHELD_SYNTHETIC_DETAIL" not in response.text
    assert state["output"]["reply"] == "WITHHELD_SYNTHETIC_DETAIL"


def test_new_turn_resets_stale_approval_without_erasing_internal_output() -> None:
    previous = completed_state()

    async def intake_only(input_state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        assert input_state["approved"] is False
        assert input_state["delivery_hold"] is True
        assert "output" not in input_state
        return {**previous, **input_state, "missing_fields": ["age"]}

    graph = SimpleNamespace(
        aget_state=AsyncMock(return_value=SimpleNamespace(values=previous)),
        ainvoke=AsyncMock(side_effect=intake_only),
    )
    with patch("app.api.v1.message._app_graph", graph):
        response = TestClient(app).post(
            "/v1/message", json={"session_id": "held", "user_message": "Hello"}
        )
    assert response.status_code == 200
    assert response.json()["delivery_hold"] is True
    assert "WITHHELD_SYNTHETIC_DETAIL" not in response.text


def test_report_runs_unconditionally_before_delivery_gate() -> None:
    graph = build_graph().get_graph()
    edges = {(edge.source, edge.target) for edge in graph.edges}
    assert ("guardrail", "explanation_report") in edges
    assert ("explanation_report", "escalate") in edges
    assert ("escalate", "persist_memory") in edges
    assert ("persist_memory", "__end__") in edges


def test_incomplete_report_fails_closed_at_api_boundary() -> None:
    state = {**completed_state(), "output": {"report_status": "insufficient_verified_evidence"}}
    response = build_message_response("delivery-test", state)
    assert response.delivery_hold is True
    assert response.output == {}
