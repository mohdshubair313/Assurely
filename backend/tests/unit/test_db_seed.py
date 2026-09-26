"""Unit tests for seed data integrity and schema validation."""

from typing import Any, cast

import pytest
from app.db.seed import SEED_POLICIES
from app.models.db.policy_terms import PolicyTerms
from app.models.db.policy_document import PolicyDocument
from app.models.db.audit_log import AuditLog
from app.models.db.session import Session
from app.models.db.user import User


def test_seed_policies_structure() -> None:
    """Verify seed policies conform to IRDAI health policy terms requirements."""
    assert len(SEED_POLICIES) == 3
    insurers = [p["insurer"] for p in SEED_POLICIES]
    assert "HDFC ERGO General Insurance" in insurers
    assert "Care Health Insurance" in insurers
    assert "Star Health and Allied Insurance" in insurers

    for p in SEED_POLICIES:
        terms: dict[str, Any] = cast(dict[str, Any], p["terms"])
        # Limits and eligibility
        assert terms["sum_insured_min"] >= 500_000
        assert terms["sum_insured_max"] >= 10_000_000
        assert terms["entry_age_min"] == 18
        assert terms["waiting_period_days_preexisting"] == 1095  # 36 months / 3 years

        # Exclusions list must be non-empty
        assert isinstance(terms["exclusions_json"], list)
        assert len(terms["exclusions_json"]) >= 3

        # Rate table must cover common age brackets
        rate_table: dict[str, Any] = cast(dict[str, Any], terms["premium_rate_table_json"])
        assert "base_5L" in rate_table or "base_10L" in rate_table
        sample_bracket: dict[str, int] = rate_table.get("base_10L", rate_table.get("base_5L", {}))
        assert "age_18_35" in sample_bracket
        assert "age_36_45" in sample_bracket


def test_models_exist_and_map_to_lld() -> None:
    """Verify all 5 target models are mapped with correct table names."""
    assert PolicyDocument.__tablename__ == "policy_documents"
    assert PolicyTerms.__tablename__ == "policy_terms"
    assert User.__tablename__ == "users"
    assert Session.__tablename__ == "sessions"
    assert AuditLog.__tablename__ == "audit_log"
