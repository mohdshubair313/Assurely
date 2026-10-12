"""Waiting-period requests must reach RAG even without a declared condition."""

from typing import Any
from unittest.mock import patch

import pytest

from app.graph.nodes.health_domain_agent import health_domain_agent_node
from app.graph.state import create_initial_state


@pytest.mark.asyncio
@pytest.mark.parametrize("ped,dependents", [(False, 0), (True, 2)])
async def test_explicit_waiting_question_supersedes_profile_queries(
    ped: bool, dependents: int
) -> None:
    question = (
        "For HDFC ERGO Optima Secure, an aggregator says the pre-existing disease "
        "waiting period is 24 months, while the insurer says 36 months. "
        "What does the policy wording say?"
    )
    state = create_initial_state("waiting-query", question)
    state["user_profile"] = {"pre_existing_conditions": ped, "dependents": dependents}
    fact: dict[str, Any] = {
        "claim": "Synthetic waiting-period wording",
        "source": "Synthetic policy Section 4.2",
        "last_verified": "2026-10-12",
        "version_hash": "fixture-hash",
    }
    with patch(
        "app.graph.nodes.health_domain_agent.retrieve_health_facts", return_value=[fact]
    ) as retrieve:
        result = await health_domain_agent_node(state)
    retrieve.assert_called_once_with(query=question, top_k=2)
    assert result == {"retrieved_facts": [fact]}


@pytest.mark.asyncio
async def test_waiting_request_survives_intake_only_followup() -> None:
    question = "What are HDFC Optima Secure's waiting-periods?"
    state = create_initial_state("waiting-intake", question)
    state["messages"] += [
        {"role": "assistant", "content": "Please provide your age and health declarations."},
        {"role": "user", "content": "I am 40. I have no pre-existing health conditions."},
    ]
    with patch(
        "app.graph.nodes.health_domain_agent.retrieve_health_facts", return_value=[]
    ) as retrieve:
        await health_domain_agent_node(state)
    retrieve.assert_called_once_with(query=question, top_k=2)


@pytest.mark.asyncio
async def test_new_question_supersedes_old_waiting_request() -> None:
    state = create_initial_state("changed-topic", "What is the waiting period?")
    state["messages"].append({"role": "user", "content": "Explain room rent limits."})
    with patch(
        "app.graph.nodes.health_domain_agent.retrieve_health_facts", return_value=[]
    ) as retrieve:
        await health_domain_agent_node(state)
    retrieve.assert_called_once_with(
        query="hospitalization room rent single private room restoration recharge",
        top_k=2,
        scope_query="Explain room rent limits.",
    )


@pytest.mark.asyncio
async def test_general_profile_query_does_not_assume_waiting_duration() -> None:
    state = create_initial_state("general-ped", "I need family health insurance.")
    state["user_profile"] = {"pre_existing_conditions": True, "dependents": 2}
    with patch(
        "app.graph.nodes.health_domain_agent.retrieve_health_facts", return_value=[]
    ) as retrieve:
        await health_domain_agent_node(state)
    queries = [call.kwargs["query"] for call in retrieve.call_args_list]
    assert len(queries) == 3
    assert "pre-existing disease waiting period specific illnesses" in queries
    assert all("36 months" not in query for query in queries)
