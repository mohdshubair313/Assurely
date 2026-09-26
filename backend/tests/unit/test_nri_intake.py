"""Regression coverage for NRI intake reaching existing escalation rules."""
import json
from unittest.mock import patch

import pytest

from app.graph.nodes.needs_intake import needs_intake_node, _rule_based_extract
from app.graph.nodes.guardrail import evaluate_escalation
from app.graph.state import create_initial_state
from app.llm.providers import LLMResult


@pytest.mark.asyncio
@pytest.mark.parametrize("model_nri", [True, None])
async def test_successful_extraction_preserves_nri_for_escalation(model_nri):
    state = create_initial_state(session_id="nri-regression", user_message="I am an NRI living in Dubai.")
    profile = {"age": 30, "city_tier": "tier_1", "dependents": 0,
               "pre_existing_conditions": False, "is_nri": model_nri}
    with patch("app.graph.nodes.needs_intake.llm_call", return_value=LLMResult(
        content=json.dumps(profile), provider="mock", model="mock", total_tokens=0,
    )):
        result = await needs_intake_node(state)
    assert result["user_profile"]["is_nri"] is True
    assert result["missing_fields"] == []
    escalated, reason = evaluate_escalation(result["user_profile"], {}, 0.95, [])
    assert escalated and "NRI" in reason


@pytest.mark.parametrize("text, expected", [
    ("I am not an NRI", False), ("I am a resident Indian", False),
    ("I am an NRI", True), ("I am living abroad", True),
    ("I am a non-resident Indian", True), ("I am a non resident Indian", True),
    ("I am not living abroad", False),
    ("I am living in Usha Nagar", None), ("I enjoy sunrises", None),
])
def test_explicit_declarations_and_negation(text, expected):
    assert _rule_based_extract(text, {}).get("is_nri") is expected


def test_residency_can_be_corrected_on_a_later_turn():
    assert _rule_based_extract("I am an NRI", {"is_nri": False})["is_nri"] is True
    assert _rule_based_extract("I am no longer an NRI", {"is_nri": True})["is_nri"] is False


def test_explicit_residency_correction_overrides_legacy_nri_flag():
    profile = {"age": 30, "is_nri": False, "nri": True}
    escalated, reason = evaluate_escalation(profile, {}, 0.95, [])
    assert escalated is False
    assert reason is None
