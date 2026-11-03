"""Profiles cannot establish policy-specific waiting periods or room entitlements."""

import pytest

from app.calculators.health_cover_sizing import calculate_health_cover_sizing
from app.calculators.risk_profile import calculate_risk_profile


@pytest.mark.parametrize("age,tier,ped", [(25, "tier_3", False), (60, "tier_1", True)])
def test_sizing_cannot_authorize_policy_terms(age, tier, ped):
    result = calculate_risk_profile({"age": age, "city_tier": tier,
                                     "pre_existing_conditions": ped})
    assert result["ped_waiting_period_months"] is None
    assert "statutory" not in result["ped_guidance"]
    assert "sum insured alone cannot determine" in result["room_rent_deduction_risk"]
    assert result["assumptions_status"] == "unverified_development_only"
    assert calculate_health_cover_sizing(age)["assumptions_status"] == result["assumptions_status"]
