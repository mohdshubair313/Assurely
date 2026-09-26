"""Unit tests for Stage 3: compare_verify node.

Tests:
    1. Hidden clause detector flags high-severity for PED users.
    2. Hidden clause detector flags eligibility blocks (age out of window).
    3. Transparency scorer decreases with more high-severity clauses.
    4. Premium lookup returns correct bracket for age + sum insured.
    5. compare_verify_node writes draft_output, hidden_clauses, transparency_scores.
    6. No ranking language anywhere in draft_output (AGENTS.md rule 1).
    7. All claims in draft_output carry source + last_verified (rule 6).
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.graph.nodes.compare_verify import (
    _check_eligibility,
    _compute_transparency_score,
    _detect_hidden_clauses,
    _lookup_premium,
    compare_verify_node,
)
from app.models.db.policy_document import PolicyDocument
from app.models.db.policy_terms import PolicyTerms


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_terms(**overrides: Any) -> PolicyTerms:
    """Build a minimal PolicyTerms mock object."""
    t = MagicMock(spec=PolicyTerms)
    t.entry_age_min = overrides.get("entry_age_min", 18)
    t.entry_age_max = overrides.get("entry_age_max", 65)
    t.waiting_period_days_preexisting = overrides.get("waiting_period_days_preexisting", 1095)
    t.sum_insured_min = overrides.get("sum_insured_min", Decimal("500000"))
    t.sum_insured_max = overrides.get("sum_insured_max", Decimal("10000000"))
    t.exclusions_json = overrides.get("exclusions_json", [
        "Cosmetic or plastic surgery",
        "Maternity expenses unless explicitly purchased as rider",
        "Obesity/weight control treatments",
    ])
    t.premium_rate_table_json = overrides.get("premium_rate_table_json", {
        "base_5L": {"age_18_35": 8200, "age_36_45": 12600, "age_46_55": 20400, "age_56_65": 34500},
        "base_10L": {"age_18_35": 11400, "age_36_45": 17100, "age_46_55": 27800, "age_56_65": 46900},
        "base_25L": {"age_18_35": 16200, "age_36_45": 24300, "age_46_55": 39500, "age_56_65": 65800},
    })
    t.effective_date = date(2024, 1, 1)
    t.expiry_date = None
    return t


def _make_doc(**overrides: Any) -> PolicyDocument:
    """Build a minimal PolicyDocument mock object."""
    d = MagicMock(spec=PolicyDocument)
    d.insurer = overrides.get("insurer", "Test Insurer")
    d.product_name = overrides.get("product_name", "Test Plan")
    return d


# ── Hidden Clause Detector ────────────────────────────────────────────────────

class TestHiddenClauseDetector:
    """Unit tests for _detect_hidden_clauses."""

    def test_ped_user_gets_high_severity_waiting_period(self) -> None:
        """User with PED should receive a high-severity clause for waiting period."""
        terms = _make_terms()
        doc = _make_doc()
        profile = {"age": 35, "pre_existing_conditions": True}
        clauses = _detect_hidden_clauses(terms, doc, profile, [])

        ped_clauses = [
            c for c in clauses
            if "pre-existing" in c["clause"].lower() or "waiting period" in c["clause"].lower()
        ]
        assert len(ped_clauses) >= 1
        assert all(c["severity"] == "high" for c in ped_clauses)

    def test_no_ped_user_gets_medium_severity_waiting_period(self) -> None:
        """User without PED should still see the waiting period at medium severity."""
        terms = _make_terms()
        doc = _make_doc()
        profile = {"age": 30, "pre_existing_conditions": False}
        clauses = _detect_hidden_clauses(terms, doc, profile, [])

        waiting_clauses = [c for c in clauses if "waiting period" in c["clause"].lower()]
        assert len(waiting_clauses) >= 1
        assert all(c["severity"] == "medium" for c in waiting_clauses)

    def test_age_below_minimum_is_high_severity(self) -> None:
        """User below entry_age_min should get a high-severity eligibility flag."""
        terms = _make_terms(entry_age_min=25)
        doc = _make_doc()
        profile = {"age": 17}
        clauses = _detect_hidden_clauses(terms, doc, profile, [])

        eligibility_clauses = [c for c in clauses if "entry age minimum" in c["clause"].lower()]
        assert len(eligibility_clauses) == 1
        assert eligibility_clauses[0]["severity"] == "high"

    def test_age_above_maximum_is_high_severity(self) -> None:
        """User above entry_age_max should get a high-severity eligibility flag."""
        terms = _make_terms(entry_age_max=65)
        doc = _make_doc()
        profile = {"age": 70}
        clauses = _detect_hidden_clauses(terms, doc, profile, [])

        eligibility_clauses = [c for c in clauses if "entry age maximum" in c["clause"].lower()]
        assert len(eligibility_clauses) == 1
        assert eligibility_clauses[0]["severity"] == "high"

    def test_maternity_exclusion_is_high_for_maternity_user(self) -> None:
        """Maternity exclusion is high-severity if profile includes maternity flag."""
        terms = _make_terms(exclusions_json=["Maternity expenses not covered"])
        doc = _make_doc()
        profile = {"age": 28, "maternity": True}
        clauses = _detect_hidden_clauses(terms, doc, profile, [])

        mat_clauses = [c for c in clauses if "maternity" in c["clause"].lower()]
        assert len(mat_clauses) >= 1
        assert all(c["severity"] == "high" for c in mat_clauses)

    def test_all_clauses_carry_source(self) -> None:
        """AGENTS.md rule 6: every clause must have source and last_verified."""
        terms = _make_terms()
        doc = _make_doc()
        profile = {"age": 35, "pre_existing_conditions": True}
        clauses = _detect_hidden_clauses(terms, doc, profile, [])

        for clause in clauses:
            assert clause.get("source"), f"Missing source on: {clause['clause']}"
            assert clause.get("last_verified"), f"Missing last_verified on: {clause['clause']}"

    def test_room_rent_rag_fact_flagged_medium(self) -> None:
        """Room-rent facts from RAG should be flagged at medium severity."""
        terms = _make_terms(exclusions_json=[])
        doc = _make_doc()
        profile = {"age": 40}
        facts = [
            {
                "claim": "Room rent capped at 1% of sum insured per day for single private room",
                "source": "HDFC ERGO Policy Wordings 2024",
                "last_verified": "2024-01-01",
            }
        ]
        clauses = _detect_hidden_clauses(terms, doc, profile, facts)

        room_clauses = [c for c in clauses if "room rent" in c["clause"].lower()]
        assert len(room_clauses) >= 1
        assert all(c["severity"] == "medium" for c in room_clauses)


# ── Transparency Scorer ───────────────────────────────────────────────────────

class TestTransparencyScorer:
    """Unit tests for _compute_transparency_score."""

    def test_zero_clauses_high_score(self) -> None:
        """Policy with no hidden clauses for this user scores very high."""
        terms = _make_terms(entry_age_max=99, sum_insured_max=Decimal("20000000"))
        score = _compute_transparency_score([], terms, {})["score"]
        assert score >= 95

    def test_high_severity_clauses_lower_score(self) -> None:
        """Each high-severity clause reduces the score by 25 points."""
        terms = _make_terms()
        high_clauses = [{"severity": "high"}, {"severity": "high"}]
        score = _compute_transparency_score(high_clauses, terms, {})["score"]
        assert score <= 60  # 100 - 2*25 = 50, plus possible bonuses

    def test_score_bounded_0_to_100(self) -> None:
        """Score must never go below 0 or above 100."""
        terms = _make_terms()
        many_clauses = [{"severity": "high"}] * 20
        score = _compute_transparency_score(many_clauses, terms, {})["score"]
        assert 0 <= score <= 100

    def test_lifetime_renewability_bonus(self) -> None:
        """entry_age_max >= 99 earns a +5 bonus (tested below the 100-cap)."""
        # Use one medium clause to bring the base below 100 before the bonus applies
        base_clauses = [{"severity": "medium"}]  # -10 from 100 = 90 before bonuses
        terms_99 = _make_terms(entry_age_max=99, sum_insured_max=Decimal("5000000"))
        terms_65 = _make_terms(entry_age_max=65, sum_insured_max=Decimal("5000000"))
        score_99 = _compute_transparency_score(base_clauses, terms_99, {})["score"]
        score_65 = _compute_transparency_score(base_clauses, terms_65, {})["score"]
        assert score_99 > score_65


# ── Premium Lookup ────────────────────────────────────────────────────────────

class TestPremiumLookup:
    """Unit tests for _lookup_premium."""

    _RATE_TABLE: dict[str, Any] = {
        "base_5L": {"age_18_35": 8200, "age_36_45": 12600, "age_46_55": 20400, "age_56_65": 34500},
        "base_10L": {"age_18_35": 11400, "age_36_45": 17100, "age_46_55": 27800, "age_56_65": 46900},
        "base_25L": {"age_18_35": 16200, "age_36_45": 24300, "age_46_55": 39500, "age_56_65": 65800},
    }

    def test_age_30_5L_bracket(self) -> None:
        """Age 30, target SI ≤ 7.5L → base_5L age_18_35 bracket."""
        result = _lookup_premium(self._RATE_TABLE, 500_000, 30)
        assert result is not None
        assert result["annual_premium_inr"] == 8200
        assert result["bracket"] == "₹5 Lakh"

    def test_age_40_10L_bracket(self) -> None:
        """Age 40, target SI in 7.5L-17.5L range → base_10L age_36_45."""
        result = _lookup_premium(self._RATE_TABLE, 1_000_000, 40)
        assert result is not None
        assert result["annual_premium_inr"] == 17100

    def test_age_70_returns_none(self) -> None:
        """Age 70 is outside the seeded rate table range."""
        result = _lookup_premium(self._RATE_TABLE, 1_000_000, 70)
        assert result is None

    def test_empty_table_returns_none(self) -> None:
        """Empty rate table returns None gracefully."""
        result = _lookup_premium({}, 1_000_000, 30)
        assert result is None

    def test_result_carries_source(self) -> None:
        """AGENTS.md rule 6: premium result must have source + last_verified."""
        result = _lookup_premium(self._RATE_TABLE, 1_000_000, 30)
        assert result is not None
        assert result.get("source")
        assert result.get("last_verified")


# ── Eligibility Helper ────────────────────────────────────────────────────────

class TestEligibility:
    """Unit tests for _check_eligibility."""

    def test_within_window_eligible(self) -> None:
        assert _check_eligibility(_make_terms(entry_age_min=18, entry_age_max=65), {"age": 35})

    def test_below_min_not_eligible(self) -> None:
        assert not _check_eligibility(_make_terms(entry_age_min=25), {"age": 20})

    def test_above_max_not_eligible(self) -> None:
        assert not _check_eligibility(_make_terms(entry_age_max=65), {"age": 70})

    def test_no_age_in_profile_assumed_eligible(self) -> None:
        """Cannot determine eligibility without age — assume eligible."""
        assert _check_eligibility(_make_terms(), {})


# ── Full Node Integration ─────────────────────────────────────────────────────

class TestCompareVerifyNode:
    """Integration tests for compare_verify_node using mocked DB."""

    def _make_mock_db_result(self) -> list[tuple[PolicyTerms, PolicyDocument]]:
        terms1 = _make_terms(entry_age_max=99, sum_insured_max=Decimal("20000000"))
        doc1 = _make_doc(insurer="HDFC ERGO", product_name="Optima Secure")
        terms2 = _make_terms()
        doc2 = _make_doc(insurer="Care Health", product_name="Care Supreme")
        return [(terms1, doc1), (terms2, doc2)]

    def _make_mock_session(
        self, rows: list[tuple[PolicyTerms, PolicyDocument]]
    ) -> MagicMock:
        mock_result = MagicMock()
        mock_result.all.return_value = rows
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        return mock_session

    @pytest.mark.asyncio
    async def test_writes_draft_output(self) -> None:
        """Node must write draft_output with need_fit_view."""
        rows = self._make_mock_db_result()
        mock_session = self._make_mock_session(rows)

        state: dict[str, Any] = {
            "session_id": "test-stage3-001",
            "user_profile": {"age": 35, "pre_existing_conditions": True, "city_tier": "1"},
            "retrieved_facts": [],
            "calculator_outputs": {
                "risk_analysis": {"risk_adjusted_sum_insured_inr": 1_500_000}
            },
        }

        with patch("app.graph.nodes.compare_verify.AsyncSessionLocal", return_value=mock_session):
            result = await compare_verify_node(state)  # type: ignore[arg-type]

        assert "draft_output" in result
        draft = result["draft_output"]
        assert "need_fit_view" in draft
        assert len(draft["need_fit_view"]) == 2
        assert draft["total_policies_evaluated"] == 2

    @pytest.mark.asyncio
    async def test_writes_hidden_clauses(self) -> None:
        """Node must write hidden_clauses keyed by policy."""
        rows = self._make_mock_db_result()
        mock_session = self._make_mock_session(rows)

        state: dict[str, Any] = {
            "session_id": "test-stage3-002",
            "user_profile": {"age": 40, "pre_existing_conditions": True},
            "retrieved_facts": [],
            "calculator_outputs": {"risk_analysis": {"risk_adjusted_sum_insured_inr": 1_000_000}},
        }

        with patch("app.graph.nodes.compare_verify.AsyncSessionLocal", return_value=mock_session):
            result = await compare_verify_node(state)  # type: ignore[arg-type]

        assert "hidden_clauses" in result
        assert len(result["hidden_clauses"]) == 2  # one entry per policy

    @pytest.mark.asyncio
    async def test_writes_transparency_scores(self) -> None:
        """Node must write transparency_scores as a dict[policy_key, int]."""
        rows = self._make_mock_db_result()
        mock_session = self._make_mock_session(rows)

        state: dict[str, Any] = {
            "session_id": "test-stage3-003",
            "user_profile": {"age": 30},
            "retrieved_facts": [],
            "calculator_outputs": {"risk_analysis": {"risk_adjusted_sum_insured_inr": 500_000}},
        }

        with patch("app.graph.nodes.compare_verify.AsyncSessionLocal", return_value=mock_session):
            result = await compare_verify_node(state)  # type: ignore[arg-type]

        scores = result["transparency_scores"]
        assert isinstance(scores, dict)
        for key, score in scores.items():
            assert isinstance(score, int), f"Score for {key} is not an int"
            assert 0 <= score <= 100, f"Score for {key} out of range"

    @pytest.mark.asyncio
    async def test_no_ranking_language_in_output(self) -> None:
        """AGENTS.md rule 1: no 'rank', 'ranking', 'best', 'top' in any output text."""
        rows = self._make_mock_db_result()
        mock_session = self._make_mock_session(rows)

        state: dict[str, Any] = {
            "session_id": "test-stage3-004",
            "user_profile": {"age": 35},
            "retrieved_facts": [],
            "calculator_outputs": {"risk_analysis": {"risk_adjusted_sum_insured_inr": 1_000_000}},
        }

        with patch("app.graph.nodes.compare_verify.AsyncSessionLocal", return_value=mock_session):
            result = await compare_verify_node(state)  # type: ignore[arg-type]

        import json
        import re
        # The compliance_note quotes 'best'/'top' to state they are NOT used;
        # only check user-facing output fields, not the meta-compliance disclaimer.
        draft = result["draft_output"]
        user_facing = {
            "need_fit_view": draft.get("need_fit_view", []),
            "hidden_clauses": result.get("hidden_clauses", []),
            "transparency_scores": result.get("transparency_scores", {}),
        }
        output_text = json.dumps(user_facing).lower()
        # AGENTS.md rule 1: no ranking language in user-facing output.
        forbidden_patterns = [r"\branking\b", r"\branked\b", r"\bbest\b", r"\btop\b"]
        for pattern in forbidden_patterns:
            match = re.search(pattern, output_text)
            assert not match, (
                f"Forbidden word '{match.group()}' in user-facing output "
                f"(AGENTS.md rule 1 violation)"
            )

    @pytest.mark.asyncio
    async def test_all_need_fit_entries_have_source(self) -> None:
        """AGENTS.md rule 6: every numeric claim in need_fit_view must carry source + last_verified."""
        rows = self._make_mock_db_result()
        mock_session = self._make_mock_session(rows)

        state: dict[str, Any] = {
            "session_id": "test-stage3-005",
            "user_profile": {"age": 35},
            "retrieved_facts": [],
            "calculator_outputs": {"risk_analysis": {"risk_adjusted_sum_insured_inr": 1_000_000}},
        }

        with patch("app.graph.nodes.compare_verify.AsyncSessionLocal", return_value=mock_session):
            result = await compare_verify_node(state)  # type: ignore[arg-type]

        for entry in result["draft_output"]["need_fit_view"]:
            si_range = entry["sum_insured_range_inr"]
            assert si_range.get("source"), "sum_insured_range_inr missing source"
            assert si_range.get("last_verified"), "sum_insured_range_inr missing last_verified"

            age_window = entry["entry_age_window"]
            assert age_window.get("source"), "entry_age_window missing source"
            assert age_window.get("last_verified"), "entry_age_window missing last_verified"

            wp = entry["waiting_period_days_preexisting"]
            assert wp.get("source"), "waiting_period_days_preexisting missing source"
            assert wp.get("last_verified"), "waiting_period_days_preexisting missing last_verified"

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_view(self) -> None:
        """Graceful handling when no active policy_terms rows exist."""
        mock_session = self._make_mock_session([])

        state: dict[str, Any] = {
            "session_id": "test-stage3-006",
            "user_profile": {"age": 35},
            "retrieved_facts": [],
            "calculator_outputs": {},
        }

        with patch("app.graph.nodes.compare_verify.AsyncSessionLocal", return_value=mock_session):
            result = await compare_verify_node(state)  # type: ignore[arg-type]

        assert result["draft_output"]["total_policies_evaluated"] == 0
        assert result["hidden_clauses"] == []
        assert result["transparency_scores"] == {}
