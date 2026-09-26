"""risk_analysis — sizes coverage from the user's risk profile.

Trigger: after intake (runs in parallel with domain agents in Stage 2).
Reads:   user_profile.
Writes:  calculator_outputs (risk-adjusted sizing).
Calls:   calculator functions (deterministic, zero-LLM).

This node is never used to compare or evaluate insurers — it only
determines what coverage amount and structure fits the user's risk
profile. The actual comparison happens in compare_verify.

Uses need-fit framing only — never ranking language (AGENTS.md rule 1).
All calculations are deterministic (AGENTS.md rule 5).
"""

from __future__ import annotations

import logging
from typing import Any

from app.calculators.risk_profile import calculate_risk_profile
from app.graph.state import SessionState

logger = logging.getLogger(__name__)


async def risk_analysis_node(state: SessionState) -> dict[str, Any]:
    """Execute the risk_analysis node in Stage 2 parallel fan-out.

    Computes deterministic risk-adjusted coverage metrics and updates
    state['calculator_outputs'].
    """
    user_profile = state.get("user_profile", {})
    session_id = state.get("session_id", "default_session")

    # Run deterministic risk calculations (AGENTS.md rule 5)
    risk_output = calculate_risk_profile(user_profile)

    # Preserve any existing calculator outputs from needs_intake
    existing_calcs = dict(state.get("calculator_outputs", {}))
    existing_calcs["risk_analysis"] = risk_output

    logger.info(
        "Risk analysis completed for session %s: recommended ₹%s (PED: %s, Metro: %s)",
        session_id,
        f"{risk_output['risk_adjusted_sum_insured_inr']:,}",
        risk_output["ped_risk_category"],
        "1" in str(user_profile.get("city_tier", "")),
    )

    return {"calculator_outputs": existing_calcs}
