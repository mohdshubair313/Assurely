"""Health cover sizing calculator.

Deterministic calculation — zero LLM involvement (AGENTS.md rule 5).
Estimates ideal health insurance coverage based on:
  - Age and health profile of each family member
  - City tier (metro vs. non-metro hospital costs)
  - Number of dependents
  - Existing health coverage, if any
  - Pre-existing health conditions

Used by needs_intake (once profile is complete) and risk_analysis
to provide a coverage amount recommendation grounded in arithmetic,
not LLM guesswork.
"""

from __future__ import annotations

from typing import Any


def calculate_health_cover_sizing(
    age: int,
    city_tier: str | int = "tier_1",
    dependents_count: int = 0,
    has_pre_existing_conditions: bool = False,
    existing_coverage: int = 0,
) -> dict[str, Any]:
    """Calculate recommended health insurance sum insured deterministically.

    All numbers follow Indian healthcare inflation & hospital cost benchmarks:
      - Tier 1 (Metros): base ₹10,00,000 (₹10 Lakhs)
      - Tier 2: base ₹7,50,000 (₹7.5 Lakhs)
      - Tier 3: base ₹5,00,000 (₹5 Lakhs)
    """
    tier_str = str(city_tier).lower().replace(" ", "_")
    if "1" in tier_str or "metro" in tier_str:
        base_cover = 1_000_000  # 10 Lakhs
        tier_label = "Tier 1 (Metro)"
    elif "2" in tier_str:
        base_cover = 750_000  # 7.5 Lakhs
        tier_label = "Tier 2"
    else:
        base_cover = 500_000  # 5 Lakhs
        tier_label = "Tier 3"

    # Family dependents addition
    dependent_addon = dependents_count * 250_000

    # Age multiplier
    if age >= 60:
        age_multiplier = 1.5
    elif age >= 45:
        age_multiplier = 1.25
    else:
        age_multiplier = 1.0

    gross_cover = int((base_cover + dependent_addon) * age_multiplier)

    # Pre-existing condition buffer
    if has_pre_existing_conditions:
        gross_cover += 500_000  # Additional 5 Lakh buffer for PED

    net_recommended_cover = max(500_000, gross_cover - existing_coverage)

    return {
        "calculator": "health_cover_sizing",
        "city_tier": tier_label,
        "base_cover_inr": base_cover,
        "dependent_addon_inr": dependent_addon,
        "age_multiplier": age_multiplier,
        "pre_existing_buffer_inr": 500_000 if has_pre_existing_conditions else 0,
        "gross_recommended_sum_insured_inr": gross_cover,
        "existing_coverage_inr": existing_coverage,
        "net_recommended_sum_insured_inr": net_recommended_cover,
        "formula": "((base_cover + dependents * 2.5L) * age_multiplier) + ped_buffer - existing_cover",
    }
