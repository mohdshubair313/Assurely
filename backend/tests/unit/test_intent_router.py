"""Unit tests for intent_router node and deterministic routing."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from app.graph.build_graph import build_graph, route_after_intent
from app.graph.nodes.intent_router import _rule_based_classify_intent, intent_router_node
from app.graph.state import SessionState, create_initial_state
from app.llm.providers import LLMResult


def _make_empty_db_session() -> MagicMock:
    """Return a mock AsyncSessionLocal that yields no policy_terms rows.

    Prevents asyncpg event-loop conflicts when compare_verify runs inside
    integration tests that don't need to exercise Stage 3 DB behaviour.
    """
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    return mock_session


def test_rule_based_intent_classification() -> None:
    """Verify deterministic fallback correctly identifies product keywords."""
    health_msgs = [{"role": "user", "content": "I want medical insurance for hospital bills"}]
    assert _rule_based_classify_intent(health_msgs) == "health"

    life_msgs = [
        {"role": "user", "content": "Looking for pure term life insurance for death cover"}
    ]
    assert _rule_based_classify_intent(life_msgs) == "life"

    unclear_msgs = [{"role": "user", "content": "I want some general protection"}]
    assert _rule_based_classify_intent(unclear_msgs) == "unclear"


def test_deterministic_route_after_intent() -> None:
    """Verify route_after_intent conforms strictly to AGENTS.md rule 2."""
    state_health: SessionState = {"intent": "health"}
    assert route_after_intent(state_health) == ["health_domain_agent", "risk_analysis"]

    state_life: SessionState = {"intent": "life"}
    assert route_after_intent(state_life) == "life_deferred"

    state_unclear: SessionState = {"intent": "unclear"}
    assert route_after_intent(state_unclear) == "unclear_intent"


@pytest.mark.asyncio
async def test_intent_router_node_unclear_generates_clarification() -> None:
    """Verify unclear intent appends a clarification question to messages."""
    state = create_initial_state(session_id="unclear-sess", user_message="I want family coverage")
    state["missing_fields"] = []  # profile complete

    with patch("app.graph.nodes.intent_router.llm_call") as mock_llm:
        mock_llm.return_value = LLMResult(
            content='{"intent": "unclear", "confidence": 0.5}',
            provider="mock",
            model="mock-router",
            total_tokens=20,
        )
        updates = await intent_router_node(state)
        assert updates["intent"] == "unclear"
        assert len(updates["messages"]) > len(state["messages"])
        assert "health" in updates["messages"][-1]["content"].lower()
        assert "life" in updates["messages"][-1]["content"].lower()


@pytest.mark.asyncio
async def test_graph_executes_intake_to_intent_router() -> None:
    """Verify complete profile automatically transitions from needs_intake to intent_router.

    AsyncSessionLocal is mocked to avoid asyncpg event-loop conflicts when
    the full graph routes through compare_verify (Stage 3) after health intent.
    """
    initial_state = create_initial_state(
        session_id="complete-flow-sess",
        user_message=(
            "I am 30 years old living in Bengaluru with my wife, healthy, need health insurance."
        ),
    )

    intake_json = (
        '{"age": 30, "city_tier": "tier_1", "dependents": 1, '
        '"pre_existing_conditions": false, "existing_coverage": 0}'
    )
    router_json = '{"intent": "health", "confidence": 0.95}'

    async def mock_llm_call(*args: Any, **kwargs: Any) -> LLMResult:
        task_type = kwargs.get("task_type")
        content = intake_json if task_type == "intake" else router_json
        return LLMResult(
            content=content,
            provider="mock",
            model="mock-llm",
            total_tokens=30,
        )

    mock_session = _make_empty_db_session()

    with (
        patch(
            "app.graph.build_graph.persist_memory_node",
            new=AsyncMock(return_value={"decision_trace_persisted": True}),
        ),
        patch("app.graph.nodes.needs_intake.llm_call", side_effect=mock_llm_call),
        patch("app.graph.nodes.intent_router.llm_call", side_effect=mock_llm_call),
        patch("app.graph.nodes.compare_verify.AsyncSessionLocal", return_value=mock_session),
    ):
        graph = build_graph()
        config: RunnableConfig = {"configurable": {"thread_id": "complete-flow-sess"}}
        final_state = await graph.ainvoke(initial_state, config=config)

        # Profile complete
        assert final_state["user_profile"]["age"] == 30
        assert final_state["missing_fields"] == []
        # Intent routed to health
        assert final_state["intent"] == "health"
        # Deterministic calculator output present
        assert "health_cover_sizing" in final_state["calculator_outputs"]
