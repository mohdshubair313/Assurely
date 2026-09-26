"""Unit tests for Stage 2 parallel fan-out: health_domain_agent + risk_analysis."""

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.calculators.risk_profile import calculate_risk_profile
from app.graph.build_graph import build_graph
from app.graph.nodes.health_domain_agent import health_domain_agent_node
from app.graph.nodes.risk_analysis import risk_analysis_node
from app.graph.state import create_initial_state, SessionState
from app.llm.providers import LLMResult


def _make_empty_db_session() -> MagicMock:
    """Return a mock AsyncSessionLocal that yields no policy_terms rows.

    Used in integration tests that route through compare_verify but don't
    need to exercise Stage 3 DB behaviour — avoids asyncpg event-loop
    conflicts in unit test environments.
    """
    mock_result = MagicMock()
    mock_result.all.return_value = cast(list[Any], [])
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    return mock_session


def test_risk_profile_calculator_deterministic() -> None:
    """Verify calculate_risk_profile produces deterministic arithmetic outputs (AGENTS.md rule 5)."""
    profile_metro_ped = {
        "age": 35,
        "city_tier": "tier_1",
        "dependents": 2,
        "pre_existing_conditions": True,
        "existing_coverage": 0,
    }
    result = calculate_risk_profile(profile_metro_ped)
    assert result["calculator"] == "risk_analysis"
    assert result["tertiary_care_benchmark_inr"] == 1_500_000
    assert result["ped_risk_category"] == "High"
    assert result["ped_waiting_period_months"] == 36
    assert result["risk_adjusted_sum_insured_inr"] >= 1_500_000
    assert result["projected_5yr_inr"] > result["base_cover_inr"]

    # Rule 1 compliance: zero ranking language
    for k, v in result.items():
        if isinstance(v, str):
            for banned in ["rank", "ranking", "best", "top"]:
                assert banned not in v.lower(), f"Banned word '{banned}' in {k}"


@pytest.mark.asyncio
async def test_health_domain_agent_retrieval() -> None:
    """Verify health_domain_agent populates retrieved_facts with valid citations (AGENTS.md rule 6)."""
    state = create_initial_state(session_id="test-health-domain", user_message="I need family health insurance")
    state["intent"] = "health"
    state["user_profile"] = {
        "age": 32,
        "city_tier": "tier_1",
        "dependents": 2,
        "pre_existing_conditions": True,
    }

    result = await health_domain_agent_node(state)
    assert "retrieved_facts" in result
    facts = result["retrieved_facts"]
    assert len(facts) >= 1

    for fact in facts:
        # AGENTS.md rule 6: every claim carries source and last-verified date
        assert "claim" in fact and len(fact["claim"]) > 10
        assert "source" in fact and len(fact["source"]) > 5
        assert "last_verified" in fact and len(fact["last_verified"]) > 0
        assert "retrieved_at" in fact

        # AGENTS.md rule 1: neutral language only
        for banned in ["rank", "ranking", "best", "top"]:
            assert banned not in fact["claim"].lower()


@pytest.mark.asyncio
async def test_stage2_parallel_fanout_execution() -> None:
    """Verify graph executes Stage 2 fan-out (health_domain_agent + risk_analysis)
    and Stage 3 fan-in (compare_verify) in a single multi-node turn.

    AsyncSessionLocal is mocked with empty results so compare_verify completes
    without a real DB connection (avoids asyncpg event-loop conflicts in unit tests).
    """
    graph = build_graph()

    initial_state = create_initial_state(
        session_id="fanout-test-session",
        user_message="I am 34 years old living in Mumbai with 1 child, healthy, looking for medical insurance.",
    )

    intake_json = '{"age": 34, "city_tier": "tier_1", "dependents": 1, "pre_existing_conditions": false, "existing_coverage": 0}'
    router_json = '{"intent": "health", "confidence": 0.99}'

    async def mock_llm_call(*args: Any, **kwargs: Any) -> LLMResult:
        task_type = kwargs.get("task_type")
        content = intake_json if task_type == "intake" else router_json
        return LLMResult(
            content=content,
            provider="mock",
            model="mock-llm",
            total_tokens=25,
        )

    mock_session = _make_empty_db_session()

    with patch("app.graph.nodes.needs_intake.llm_call", side_effect=mock_llm_call), \
         patch("app.graph.nodes.intent_router.llm_call", side_effect=mock_llm_call), \
         patch("app.graph.nodes.compare_verify.AsyncSessionLocal", return_value=mock_session):

        config = {"configurable": {"thread_id": "fanout-test-session"}}
        final_state = await graph.ainvoke(initial_state, config=config)

        # 1. Profile and intent completed
        assert final_state["missing_fields"] == []
        assert final_state["intent"] == "health"

        # 2. health_domain_agent populated retrieved_facts
        assert len(final_state.get("retrieved_facts", [])) >= 1
        first_fact = final_state["retrieved_facts"][0]
        assert "claim" in first_fact
        assert "source" in first_fact
        assert "last_verified" in first_fact

        # 3. risk_analysis populated calculator_outputs
        calcs = final_state.get("calculator_outputs", {})
        assert "risk_analysis" in calcs
        risk = calcs["risk_analysis"]
        assert risk["calculator"] == "risk_analysis"
        assert risk["risk_adjusted_sum_insured_inr"] >= 1_000_000

        # 4. compare_verify (Stage 3) wrote its output fields
        draft = final_state.get("draft_output", {})
        assert draft.get("stage") == "compare_verify"
        assert draft.get("total_policies_evaluated") == 0  # empty mock DB
        assert isinstance(final_state.get("hidden_clauses"), list)
        assert isinstance(final_state.get("transparency_scores"), dict)
