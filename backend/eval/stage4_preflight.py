"""Reproducible synthetic Stage 4 evidence; no model or database calls.

Run from backend: python -m eval.stage4_preflight
Scores measure the current heuristic, not a calibrated probability.
"""

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.graph.nodes.guardrail import calculate_confidence_score, guardrail_node
from app.graph.state import create_initial_state


async def main() -> None:
    draft: dict[str, Any] = {
        "need_fit_view": [
            {
                "product_name": "Synthetic incomplete policy",
                "eligible": True,
                "sum_insured_range_inr": {"min": 500000, "max": 10000000},
            }
        ],
        "cited_facts": [
            {
                "claim": "Synthetic policy waiting period is 24 months",
                "source": "Synthetic source A",
                "conflict": True,
            },
            {
                "claim": "Synthetic policy waiting period is 36 months",
                "source": "Synthetic source B",
                "conflict": True,
            },
        ],
    }
    profile = {"age": 30}
    score = calculate_confidence_score(draft, [], profile)
    state = create_initial_state(session_id="stage4-low-confidence-preflight")
    state["user_profile"] = profile
    state["draft_output"] = draft
    result = await guardrail_node(state)
    # Keep provenance intact while omitting actual age/waiting/premium values:
    # this isolates the completeness/conflict score from citation rejection.
    sourced_draft = deepcopy(draft)
    provenance = {"source": "Synthetic test fixture", "last_verified": "2026-09-25"}
    policy = sourced_draft["need_fit_view"][0]
    policy["sum_insured_range_inr"].update(provenance)
    policy["entry_age_window"] = dict(provenance)
    policy["waiting_period_days_preexisting"] = dict(provenance)
    for fact in sourced_draft["cited_facts"]:
        fact["last_verified"] = provenance["last_verified"]
    state["draft_output"] = sourced_draft
    sourced_result = await guardrail_node(state)
    control = deepcopy(sourced_draft)
    control_policy = control["need_fit_view"][0]
    control_policy["entry_age_window"].update(min=18, max=65)
    control_policy["waiting_period_days_preexisting"]["value"] = 1095
    control_policy["premium_estimate"] = {**provenance, "annual_premium_inr": 10000}
    complete_profile = {
        "age": 30,
        "city_tier": "tier_1",
        "dependents": 0,
        "pre_existing_conditions": False,
    }
    conflict_only = calculate_confidence_score(control, [], complete_profile)
    control["cited_facts"] = [{**provenance, "claim": "Synthetic consistent wording"}]
    complete_control = calculate_confidence_score(control, [], complete_profile)
    record = {
        "executed_at": datetime.now(UTC).isoformat(),
        "case": "Incomplete profile, missing policy fields, explicit conflicting evidence",
        "synthetic_fixture": True,
        "profile": profile,
        "draft": draft,
        "formula_without_compliance_violations": score,
        "guardrail_result": result,
        "sourced_but_incomplete_draft": sourced_draft,
        "sourced_but_incomplete_guardrail_result": sourced_result,
        "complete_profile_and_terms_with_conflict_score": conflict_only,
        "complete_consistent_control_score": complete_control,
        "limitation": (
            "Heuristic only. Explicit conflict flag is supplied by this fixture; "
            "this does not prove automatic contradiction detection."
        ),
    }
    assert score == 0.46 and score < 0.70
    assert result["escalation"] is True and result["approved"] is False
    assert "Confidence score calculated: 0.00" in result["guardrail_notes"]
    assert "output" not in result
    assert "Confidence score calculated: 0.46" in sourced_result["guardrail_notes"]
    assert sourced_result["escalation"] is True
    assert "Low confidence score (0.46" in sourced_result["escalation_reason"]
    assert conflict_only == 0.88 and complete_control == 1.0
    target = Path(__file__).resolve().parents[2] / "artifacts" / "stage4-preflight.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
