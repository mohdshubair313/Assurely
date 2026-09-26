"""Unit tests for SessionState, needs_intake, and basic graph execution."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.graph.build_graph import build_graph, route_after_intake
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


def test_initial_state_defaults() -> None:
    """Verify create_initial_state populates all LLD § 7.1 fields."""
    state = create_initial_state(session_id="test-session-123", user_message="Hello")
    assert state["session_id"] == "test-session-123"
    assert len(state["messages"]) == 1
    assert state["messages"][0]["content"] == "Hello"
    assert "age" in state["missing_fields"]
    assert state["approved"] is False
    assert state["escalation"] is False
    assert state["output"] == {}


def test_deterministic_route_after_intake() -> None:
    """Verify route_after_intake is purely deterministic (AGENTS.md rule 2)."""
    state_incomplete: SessionState = {"missing_fields": ["age", "city_tier"]}
    assert route_after_intake(state_incomplete) == "continue_intake"

    state_complete: SessionState = {"missing_fields": []}
    assert route_after_intake(state_complete) == "route_intent"


@pytest.mark.asyncio
async def test_graph_execution_single_node() -> None:
    """Verify compiled graph runs needs_intake with fallback chain and deterministic calculator.

    AsyncSessionLocal is mocked to avoid asyncpg event-loop conflicts when
    the full graph routes through compare_verify (Stage 3) after profile completion.
    """
    graph = build_graph()

    # Provide all required info in the user message so profile completes in one turn
    initial_state = create_initial_state(
        session_id="test-intake-session",
        user_message="I am 35 years old living in Mumbai with no pre-existing health issue. Myself only.",
    )

    mock_llm_json = '{"age": 35, "city_tier": "tier_1", "dependents": 0, "pre_existing_conditions": false, "existing_coverage": 0}'

    mock_session = _make_empty_db_session()

    with patch("app.llm.fallback_chain.llm_call") as mock_llm, \
         patch("app.graph.nodes.compare_verify.AsyncSessionLocal", return_value=mock_session):
        mock_llm.return_value = LLMResult(
            content=mock_llm_json,
            provider="mock",
            model="mock-groq",
            total_tokens=42,
        )

        config = {"configurable": {"thread_id": "test-intake-session"}}
        result = await graph.ainvoke(initial_state, config=config)

        # Profile should be populated
        assert result["user_profile"]["age"] == 35
        assert result["user_profile"]["city_tier"] == "tier_1"
        assert result["missing_fields"] == []

        # Deterministic calculator output must be present (AGENTS.md rule 5)
        calcs = result.get("calculator_outputs", {})
        assert "health_cover_sizing" in calcs
        sizing = calcs["health_cover_sizing"]
        assert sizing["base_cover_inr"] == 1_000_000  # 10L for Tier 1
        assert sizing["net_recommended_sum_insured_inr"] >= 1_000_000
