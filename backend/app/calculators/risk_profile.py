"""Risk profile and coverage sizing analysis calculator.

Deterministic calculation — zero LLM involvement (AGENTS.md rule 5).
Evaluates medical inflation, pre-existing disease exposure, tertiary care
thresholds, and room-rent proportionate deduction vulnerability.

Used by the risk_analysis node in Stage 2 parallel fan-out.
"""

from __future__ import annotations

from typing import Any

from app.calculators.health_cover_sizing import calculate_health_cover_sizing


def calculate_risk_profile(user_profile: dict[str, Any]) -> dict[str, Any]:
    """Calculate deterministic risk-adjusted coverage metrics from user profile.

    AGENTS.md rule 1: Neutral need-fit framing only — zero ranking language.
    AGENTS.md rule 5: Deterministic math only — zero LLM-invented numbers.
    """
    age = int(user_profile.get("age", 30))
    city_tier = str(user_profile.get("city_tier", "tier_1"))
    dependents = int(user_profile.get("dependents", 0))
    has_ped = bool(user_profile.get("pre_existing_conditions", False))
    existing_coverage = int(user_profile.get("existing_coverage", 0))

    # 1. Base health cover sizing
    base_sizing = calculate_health_cover_sizing(
        age=age,
        city_tier=city_tier,
        dependents_count=dependents,
        has_pre_existing_conditions=has_ped,
        existing_coverage=existing_coverage,
    )
    base_net = base_sizing.get("net_recommended_sum_insured_inr", 1_000_000)

    # 2. Medical inflation projection (14% p.a. Indian healthcare inflation benchmark)
    inflation_rate = 0.14
    five_year_multiplier = round((1.0 + inflation_rate) ** 5, 2)  # ~1.93x
    projected_5yr_cost = int(base_net * five_year_multiplier)

    # 3. Tertiary care exposure threshold
    is_metro = "1" in city_tier.lower() or "metro" in city_tier.lower()
    tertiary_care_min_inr = 1_500_000 if is_metro else 1_000_000

    # 4. Pre-existing condition risk factor
    ped_risk_category = "High" if has_ped else "Standard"
    ped_waiting_period_months = 36  # Standard statutory benchmark
    ped_advice = (
        "Out-of-pocket exposure exists during statutory 36-month waiting period; "
        "consider reduced waiting period or restoration riders."
        if has_ped
        else "Standard statutory waiting period applies."
    )

    # 5. Room rent proportionate deduction risk
    room_rent_risk = (
        "High risk of proportionate deductions if policy caps room rent at 1% of Sum Insured."
        if base_net < 1_000_000
        else "Sum insured sufficient for single private room without proportionate deductions."
    )

    # 6. Risk-adjusted recommended sum insured
    risk_adjusted_sum_insured = max(base_net, tertiary_care_min_inr)

    return {
        "calculator": "risk_analysis",
        "risk_adjusted_sum_insured_inr": risk_adjusted_sum_insured,
        "base_cover_inr": base_net,
        "projected_5yr_inr": projected_5yr_cost,
        "medical_inflation_rate_annual": inflation_rate,
        "tertiary_care_benchmark_inr": tertiary_care_min_inr,
        "ped_risk_category": ped_risk_category,
        "ped_waiting_period_months": ped_waiting_period_months,
        "ped_guidance": ped_advice,
        "room_rent_deduction_risk": room_rent_risk,
        "formula": "max(base_sizing_net, tertiary_care_benchmark)",
    }
