"""Exercise the actual Stage 3 to Stage 4 evidence and scoring contract."""

from copy import deepcopy
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.graph.nodes.compare_verify import compare_verify_node
from app.graph.nodes.guardrail import calculate_confidence_score, guardrail_node
from app.graph.state import SessionState, create_initial_state


def complete_profile() -> dict[str, Any]:
    return {"age": 30, "city_tier": "tier_1", "dependents": 0, "pre_existing_conditions": False}


async def projected_draft(
    profile: dict[str, Any], *, incomplete: bool = False, conflict: bool = False
) -> SessionState:
    terms = MagicMock()
    terms.sum_insured_min = 500000
    terms.sum_insured_max = 10000000
    terms.entry_age_min = None if incomplete else 18
    terms.entry_age_max = None if incomplete else 65
    terms.waiting_period_days_preexisting = None if incomplete else 1095
    terms.premium_rate_table_json = {} if incomplete else {"base_10L": {"age_18_35": 10000}}
    terms.exclusions_json = []
    terms.effective_date = "2026-09-26"
    doc = MagicMock(insurer="Synthetic insurer", product_name="Synthetic policy")
    db_result = MagicMock()
    db_result.all.return_value = [(terms, doc)]
    session = AsyncMock()
    session.execute.return_value = db_result
    session.__aenter__.return_value = session
    state = create_initial_state(session_id="confidence-contract")
    state["user_profile"] = profile
    state["retrieved_facts"] = [
        {
            "claim": "Synthetic clause wording requiring review",
            "source": "Synthetic test evidence",
            "last_verified": "2026-09-26",
            "conflict": conflict,
        }
    ]
    original_facts = deepcopy(state["retrieved_facts"])
    with patch("app.graph.nodes.compare_verify.AsyncSessionLocal", return_value=session):
        updates = await compare_verify_node(state)
    assert state["retrieved_facts"] == original_facts
    state.update(
        {
            "draft_output": updates["draft_output"],
            "hidden_clauses": updates["hidden_clauses"],
            "transparency_scores": updates["transparency_scores"],
        }
    )
    return state


@pytest.mark.asyncio
async def test_conflicts_survive_projection_and_lower_actual_guardrail_score() -> None:
    clean = await projected_draft(complete_profile())
    conflicted = await projected_draft(complete_profile(), conflict=True)
    assert conflicted["draft_output"]["cited_facts"][0]["conflict"] is True
    assert "Confidence score calculated: 1.00" in (await guardrail_node(clean))["guardrail_notes"]
    assert (
        "Confidence score calculated: 0.88" in (await guardrail_node(conflicted))["guardrail_notes"]
    )


@pytest.mark.asyncio
async def test_projected_incomplete_conflicting_case_escalates_with_actual_number() -> None:
    state = await projected_draft({"age": 30}, incomplete=True, conflict=True)
    snapshot = state["draft_output"]["user_profile_snapshot"]
    assert snapshot["dependents"] is None
    assert snapshot["pre_existing_conditions"] is None
    result = await guardrail_node(state)
    assert "Confidence score calculated: 0.46" in result["guardrail_notes"]
    assert result["escalation"] is True
    assert "Low confidence score (0.46" in result["escalation_reason"]
    assert "output" not in result


@pytest.mark.asyncio
async def test_missing_profile_gets_no_credit_from_stale_snapshot() -> None:
    state = await projected_draft(complete_profile())
    draft = state["draft_output"]
    assert calculate_confidence_score(draft, [], {}) == 0.80
    draft.pop("user_profile_snapshot")
    assert calculate_confidence_score(draft, []) == 0.80


@pytest.mark.asyncio
async def test_real_premium_field_counts_towards_completeness() -> None:
    state = await projected_draft(complete_profile())
    draft = state["draft_output"]
    assert draft["need_fit_view"][0]["premium_estimate"]["annual_premium_inr"] == 10000
    assert calculate_confidence_score(draft, []) == 1.00
    draft["need_fit_view"][0]["premium_estimate"] = None
    assert calculate_confidence_score(draft, []) == 0.91


@pytest.mark.asyncio
async def test_unknown_city_is_not_a_completed_declaration() -> None:
    state = await projected_draft(complete_profile())
    profile = {**complete_profile(), "city_tier": "unknown"}
    assert calculate_confidence_score(state["draft_output"], [], profile) == 0.95
