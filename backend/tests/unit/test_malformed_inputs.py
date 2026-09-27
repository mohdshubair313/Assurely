"""Regression checks for malformed extracted profiles and policy numeric terms."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.graph.nodes.guardrail import check_ranking_language, guardrail_node
from app.graph.nodes.health_domain_agent import health_domain_agent_node
from app.graph.nodes.needs_intake import needs_intake_node
from app.graph.state import create_initial_state


def _profile() -> dict[str, Any]:
    return {
        "age": 35,
        "city_tier": "tier_1",
        "dependents": 0,
        "pre_existing_conditions": False,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("age", "thirty"),
        ("age", True),
        ("dependents", -2),
        ("dependents", 1.5),
        ("city_tier", ["tier_1"]),
        ("pre_existing_conditions", "false"),
    ],
)
async def test_invalid_extracted_field_requests_clarification(field: str, value: Any) -> None:
    profile = {**_profile(), field: value}
    state = create_initial_state("malformed-profile", "Please review my coverage.")
    with patch(
        "app.graph.nodes.needs_intake.llm_call",
        AsyncMock(return_value=MagicMock(content=json.dumps(profile))),
    ):
        result = await needs_intake_node(state)

    assert result["missing_fields"] == [field]
    assert field not in result["user_profile"]
    assert "calculator_outputs" not in result
    assert result["messages"][-1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_numeric_strings_are_normalized_before_downstream_nodes() -> None:
    profile = {**_profile(), "age": "35", "dependents": "2", "existing_coverage": "100000"}
    state = create_initial_state("numeric-profile", "Please review my coverage.")
    with patch(
        "app.graph.nodes.needs_intake.llm_call",
        AsyncMock(return_value=MagicMock(content=json.dumps(profile))),
    ):
        result = await needs_intake_node(state)

    assert result["missing_fields"] == []
    assert result["user_profile"]["dependents"] == 2
    assert result["user_profile"]["age"] == 35
    assert result["user_profile"]["existing_coverage"] == 100000
    state["user_profile"] = result["user_profile"]
    with patch("app.graph.nodes.health_domain_agent.retrieve_health_facts", return_value=[]):
        assert await health_domain_agent_node(state) == {"retrieved_facts": []}


@pytest.mark.asyncio
async def test_invalid_optional_coverage_does_not_crash_calculator() -> None:
    state = create_initial_state("optional-profile")
    state["user_profile"] = {**_profile(), "existing_coverage": None}
    result = await needs_intake_node(state)
    assert result["calculator_outputs"]["health_cover_sizing"]["existing_coverage_inr"] == 0


def _draft() -> dict[str, Any]:
    provenance = {"source": "Synthetic test fixture", "last_verified": "2026-09-27"}
    return {
        "need_fit_view": [
            {
                "product_name": "Fixture policy",
                "eligible": True,
                "sum_insured_range_inr": {"min": 500000, "max": 1000000, **provenance},
                "entry_age_window": {"min": 18, "max": 65, **provenance},
                "waiting_period_days_preexisting": {"value": 730, **provenance},
            }
        ]
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("term", "field", "value"),
    [
        ("sum_insured_range_inr", "min", "unknown"),
        ("sum_insured_range_inr", "max", float("inf")),
        ("entry_age_window", "min", True),
        ("entry_age_window", "max", "65"),
        ("waiting_period_days_preexisting", "value", float("nan")),
    ],
)
async def test_invalid_numeric_terms_are_rejected_without_exception(
    term: str, field: str, value: Any
) -> None:
    state = create_initial_state("malformed-terms")
    state["user_profile"] = _profile()
    state["draft_output"] = _draft()
    state["draft_output"]["need_fit_view"][0][term][field] = value
    result = await guardrail_node(state)
    assert result["approved"] is False
    assert result["escalation"] is True
    assert "output" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, "unknown", [1, 2]])
async def test_malformed_term_containers_fail_provenance_without_exception(value: Any) -> None:
    state = create_initial_state("malformed-container")
    state["user_profile"] = _profile()
    state["draft_output"] = _draft()
    state["draft_output"]["need_fit_view"][0]["sum_insured_range_inr"] = value
    result = await guardrail_node(state)
    assert result["approved"] is False
    assert result["escalation"] is True


@pytest.mark.asyncio
async def test_null_numeric_values_remain_unknown_and_trigger_low_confidence() -> None:
    state = create_initial_state("missing-numbers")
    state["user_profile"] = _profile()
    state["draft_output"] = _draft()
    policy = state["draft_output"]["need_fit_view"][0]
    for term in ("sum_insured_range_inr", "entry_age_window"):
        policy[term].update(min=None, max=None)
    policy["waiting_period_days_preexisting"]["value"] = None
    result = await guardrail_node(state)
    assert result["escalation"] is True
    assert "0.40" in result["escalation_reason"]


def test_symbol_prefixed_prohibited_phrase_is_detected() -> None:
    assert check_ranking_language("Our #1 policy")
    assert not check_ranking_language("Refer to clause #10.")
