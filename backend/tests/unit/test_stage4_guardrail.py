"""Unit tests for Stage 4: guardrail node (compliance & advisor escalation).

Tests:
    1. Prohibited ranking words detection (AGENTS.md rule 1).
    2. Unlicensed advice detection.
    3. Provenance & citation verification (AGENTS.md rule 6).
    4. Deterministic numeric sanity checks (AGENTS.md rule 5).
    5. Confidence score calculation.
    6. Advisor escalation triggers:
       - Pre-existing conditions (PED)
       - Senior citizen applicant (age >= 60)
       - High sum insured (>= ₹1 Crore)
       - Zero eligible policies
       - Compliance violations
    7. CRITICAL CONTRACT (AGENTS.md rule 4):
       - guardrail sets approved, escalation, escalation_reason, guardrail_notes.
       - guardrail NEVER writes output.
    8. End-to-end LangGraph wiring through Stage 4.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from app.graph.build_graph import build_graph
from app.graph.nodes.guardrail import (
    HIGH_VALUE_COVER_THRESHOLD_INR,
    SENIOR_CITIZEN_AGE_THRESHOLD,
    calculate_confidence_score,
    check_numeric_hallucinations,
    check_provenance_and_citations,
    check_ranking_language,
    check_unlicensed_advice,
    evaluate_escalation,
    guardrail_node,
)
from app.graph.state import create_initial_state

# ── Helpers & Fixtures ────────────────────────────────────────────────────────


def _make_clean_draft_output() -> dict[str, Any]:
    """Generate a valid, fully-sourced draft_output matching Stage 3 output format."""
    return {
        "stage": "compare_verify",
        "generated_at": "2026-09-21T12:00:00Z",
        "user_profile_snapshot": {
            "age": 35,
            "city_tier": "tier_1",
            "dependents": 2,
            "pre_existing_conditions": False,
        },
        "risk_adjusted_target_si_inr": {
            "value": 1500000,
            "source": "app.calculators.risk_profile (deterministic)",
            "last_verified": "2026-09-21",
        },
        "need_fit_view": [
            {
                "insurer": "HDFC ERGO",
                "product_name": "Optima Secure",
                "eligible": True,
                "sum_insured_range_inr": {
                    "min": 500000,
                    "max": 20000000,
                    "source": "policy_terms table (InsuranceAI DB)",
                    "last_verified": "2024-01-01",
                },
                "entry_age_window": {
                    "min": 18,
                    "max": 65,
                    "source": "policy_terms table (InsuranceAI DB)",
                    "last_verified": "2024-01-01",
                },
                "waiting_period_days_preexisting": {
                    "value": 1095,
                    "source": "policy_terms table (InsuranceAI DB)",
                    "last_verified": "2024-01-01",
                },
                "effective_date": "2024-01-01",
                "premium_estimate": {
                    "annual_premium_inr": 18450,
                    "source": "policy_terms table (InsuranceAI DB)",
                    "last_verified": "2024-01-01",
                },
                "transparency_score": 55,
                "hidden_clause_count": {"high": 0, "medium": 1, "low": 2},
                "fit_notes": ["No clauses directly conflict with stated profile at this time."],
            }
        ],
        "cited_facts": [
            {
                "claim": "No room rent sub-limit applicable on single private room",
                "source": "HDFC ERGO Policy Wording Section 4.2",
                "url": "https://hdfcergo.com/optima-secure.pdf",
                "last_verified": "2024-01-01",
            }
        ],
        "total_policies_evaluated": 1,
        "compliance_note": "Need-fit framing only. No policy is ranked or endorsed as best.",
    }


def _make_clean_hidden_clauses() -> list[dict[str, Any]]:
    return [
        {
            "policy_key": "HDFC ERGO|Optima Secure",
            "clauses": [
                {
                    "clause": "36-month waiting period on pre-existing conditions",
                    "severity": "medium",
                    "reason": "Standard waiting period",
                    "source": "policy_terms table (InsuranceAI DB)",
                    "last_verified": "2024-01-01",
                }
            ],
        }
    ]


def _make_empty_db_session() -> MagicMock:
    """Mock DB session preventing asyncpg calls during integration tests."""
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=mock_session)
    return mock_session


# ── Test Classes ─────────────────────────────────────────────────────────────


class TestRankingLanguageCheck:
    """AGENTS.md rule 1: Never use 'rank', 'ranking', 'best', or 'top'."""

    def test_detects_prohibited_words(self) -> None:
        assert len(check_ranking_language("This is our best policy")) > 0
        assert len(check_ranking_language("We rank this policy #1")) > 0
        assert len(check_ranking_language("Top rated health plan")) > 0
        assert len(check_ranking_language("This plan outranks other options")) > 0

    def test_passes_clean_need_fit_language(self) -> None:
        assert check_ranking_language("Need-fit evaluation for your family size.") == []
        assert (
            check_ranking_language("Features 36-month waiting period with full restoration.") == []
        )
        assert check_ranking_language("Coverage option aligned with stated requirements.") == []

    def test_word_boundaries_prevent_false_positives(self) -> None:
        # 'stop', 'tank', 'desktop' should not trigger 'top' or 'rank'
        assert check_ranking_language("Please stop by the hospital") == []
        assert check_ranking_language("Water storage tank") == []
        assert check_ranking_language("Desktop view") == []


class TestUnlicensedAdviceCheck:
    """IRDAI compliance check: blocks promissory statements."""

    def test_detects_unlicensed_advice(self) -> None:
        assert len(check_unlicensed_advice("We offer a guaranteed return on this plan")) > 0
        assert len(check_unlicensed_advice("You must buy this policy today")) > 0
        assert len(check_unlicensed_advice("This is an unconditional coverage guarantee")) > 0

    def test_passes_informative_statements(self) -> None:
        assert check_unlicensed_advice("Room rent limits apply as per Section 2.") == []


class TestProvenanceAndCitations:
    """AGENTS.md rule 6: Every claim in output carries source and last_verified."""

    def test_passes_clean_provenance(self) -> None:
        draft = _make_clean_draft_output()
        clauses = _make_clean_hidden_clauses()
        violations = check_provenance_and_citations(draft, clauses)
        assert violations == []

    def test_flags_missing_source_in_policy_terms(self) -> None:
        draft = _make_clean_draft_output()
        draft["need_fit_view"][0]["sum_insured_range_inr"]["source"] = ""
        violations = check_provenance_and_citations(draft, [])
        assert any("missing 'source'" in v for v in violations)

    def test_flags_missing_last_verified_in_policy_terms(self) -> None:
        draft = _make_clean_draft_output()
        draft["need_fit_view"][0]["waiting_period_days_preexisting"]["last_verified"] = ""
        violations = check_provenance_and_citations(draft, [])
        assert any("missing 'last_verified'" in v for v in violations)

    def test_flags_missing_source_in_cited_facts(self) -> None:
        draft = _make_clean_draft_output()
        draft["cited_facts"][0]["source"] = ""
        violations = check_provenance_and_citations(draft, [])
        assert any("Cited fact [0] missing 'source'" in v for v in violations)

    def test_flags_missing_last_verified_in_hidden_clauses(self) -> None:
        draft = _make_clean_draft_output()
        clauses = _make_clean_hidden_clauses()
        clauses[0]["clauses"][0]["last_verified"] = ""
        violations = check_provenance_and_citations(draft, clauses)
        assert any("missing 'last_verified'" in v for v in violations)


class TestNumericSanityChecks:
    """AGENTS.md rule 5: Verify sanity of deterministic numbers."""

    def test_passes_valid_bounds(self) -> None:
        draft = _make_clean_draft_output()
        assert check_numeric_hallucinations(draft) == []

    def test_flags_min_si_exceeding_max(self) -> None:
        draft = _make_clean_draft_output()
        draft["need_fit_view"][0]["sum_insured_range_inr"]["min"] = 30000000
        draft["need_fit_view"][0]["sum_insured_range_inr"]["max"] = 10000000
        violations = check_numeric_hallucinations(draft)
        assert any("min sum insured (30000000) exceeds max (10000000)" in v for v in violations)

    def test_flags_negative_waiting_period(self) -> None:
        draft = _make_clean_draft_output()
        draft["need_fit_view"][0]["waiting_period_days_preexisting"]["value"] = -30
        violations = check_numeric_hallucinations(draft)
        assert any("waiting period cannot be negative" in v for v in violations)


class TestConfidenceScoreCalculation:
    """Feeds into Human Advisor Escalation rule."""

    def test_clean_draft_gives_high_confidence(self) -> None:
        draft = _make_clean_draft_output()
        score = calculate_confidence_score(draft, violations=[])
        assert score >= 0.90

    def test_violations_reduce_confidence_below_threshold(self) -> None:
        draft = _make_clean_draft_output()
        violations = ["Violation 1", "Violation 2"]
        score = calculate_confidence_score(draft, violations)
        assert score < 0.70

    def test_low_confidence_on_missing_fields_and_conflicting_sources(self) -> None:
        """Specifically designed test case producing low confidence score."""
        draft = {
            "need_fit_view": [
                {
                    "product_name": "PolicyA",
                    "sum_insured_range_inr": {"min": 500000, "max": 10000000},
                    # Missing entry_age_window, waiting_period, premium_estimate
                }
            ],
            "cited_facts": [{"claim": "test", "source": "test", "conflict": True}],
        }
        incomplete_profile = {"age": 30}  # missing city_tier, dependents, PED
        score = calculate_confidence_score(draft, violations=[], user_profile=incomplete_profile)
        assert score == 0.46
        assert score < 0.70


class TestAdvisorEscalationTriggers:
    """LLD § 12: High-stakes and low-confidence cases escalate."""

    def test_clean_young_profile_does_not_escalate(self) -> None:
        profile = {"age": 30, "pre_existing_conditions": False}
        draft = _make_clean_draft_output()
        escalate, reason = evaluate_escalation(
            user_profile=profile,
            draft_output=draft,
            confidence_score=0.95,
            violations=[],
        )
        assert escalate is False
        assert reason is None

    def test_escalates_on_nri_status(self) -> None:
        profile = {"age": 30, "pre_existing_conditions": False, "is_nri": True}
        draft = _make_clean_draft_output()
        escalate, reason = evaluate_escalation(
            user_profile=profile,
            draft_output=draft,
            confidence_score=0.95,
            violations=[],
        )
        assert escalate is True
        assert reason is not None
        assert "Non-Resident Indian (NRI)" in reason

    def test_escalates_on_preexisting_conditions_boolean(self) -> None:
        profile = {"age": 30, "pre_existing_conditions": True}
        draft = _make_clean_draft_output()
        escalate, reason = evaluate_escalation(
            user_profile=profile,
            draft_output=draft,
            confidence_score=0.95,
            violations=[],
        )
        assert escalate is True
        assert reason is not None
        assert "pre-existing health condition" in reason

    def test_escalates_on_preexisting_conditions_text(self) -> None:
        profile = {"age": 30, "pre_existing_conditions": "Type-2 Diabetes"}
        draft = _make_clean_draft_output()
        escalate, reason = evaluate_escalation(
            user_profile=profile,
            draft_output=draft,
            confidence_score=0.95,
            violations=[],
        )
        assert escalate is True
        assert "pre-existing health condition" in cast(str, reason)

    def test_escalates_on_senior_citizen(self) -> None:
        profile = {"age": SENIOR_CITIZEN_AGE_THRESHOLD + 2, "pre_existing_conditions": False}
        draft = _make_clean_draft_output()
        escalate, reason = evaluate_escalation(
            user_profile=profile,
            draft_output=draft,
            confidence_score=0.95,
            violations=[],
        )
        assert escalate is True
        assert "senior threshold" in cast(str, reason)

    def test_escalates_on_high_sum_insured(self) -> None:
        profile = {"age": 35, "pre_existing_conditions": False}
        draft = _make_clean_draft_output()
        draft["risk_adjusted_target_si_inr"]["value"] = HIGH_VALUE_COVER_THRESHOLD_INR + 5000000
        escalate, reason = evaluate_escalation(
            user_profile=profile,
            draft_output=draft,
            confidence_score=0.95,
            violations=[],
        )
        assert escalate is True
        assert "1 Crore" in cast(str, reason)

    def test_escalates_on_zero_eligible_policies(self) -> None:
        profile = {"age": 35, "pre_existing_conditions": False}
        draft = _make_clean_draft_output()
        draft["need_fit_view"][0]["eligible"] = False
        escalate, reason = evaluate_escalation(
            user_profile=profile,
            draft_output=draft,
            confidence_score=0.95,
            violations=[],
        )
        assert escalate is True
        assert "eligibility criteria" in cast(str, reason)

    def test_escalates_on_compliance_violations(self) -> None:
        profile = {"age": 35, "pre_existing_conditions": False}
        draft = _make_clean_draft_output()
        violations = ["Prohibited ranking word detected: 'best'"]
        escalate, reason = evaluate_escalation(
            user_profile=profile,
            draft_output=draft,
            confidence_score=0.40,
            violations=violations,
        )
        assert escalate is True
        assert "Compliance violations" in cast(str, reason)


class TestGuardrailNode:
    """AGENTS.md rule 4: guardrail approves; it does NOT write output."""

    @pytest.mark.asyncio
    async def test_guardrail_node_approves_compliant_case(self) -> None:
        state = create_initial_state(session_id="test_guardrail_001")
        state["user_profile"] = {"age": 32, "pre_existing_conditions": False}
        state["draft_output"] = _make_clean_draft_output()
        state["hidden_clauses"] = _make_clean_hidden_clauses()

        result = await guardrail_node(state)

        # Contract assertion: approved is True, escalation is False
        assert result["approved"] is True
        assert result["escalation"] is False
        assert result["escalation_reason"] is None
        assert len(result["guardrail_notes"]) > 0

        # CRITICAL CONTRACT: guardrail does NOT write 'output' (AGENTS.md rule 4)
        assert "output" not in result

    @pytest.mark.asyncio
    async def test_guardrail_node_rejects_ranking_violation(self) -> None:
        state = create_initial_state(session_id="test_guardrail_002")
        state["user_profile"] = {"age": 32, "pre_existing_conditions": False}
        draft = _make_clean_draft_output()
        draft["need_fit_view"][0]["fit_notes"] = ["This is the best health policy in India."]
        state["draft_output"] = draft
        state["hidden_clauses"] = _make_clean_hidden_clauses()

        result = await guardrail_node(state)

        assert result["approved"] is False
        assert result["escalation"] is True
        assert "Compliance violations" in cast(str, result["escalation_reason"])
        assert "output" not in result

    @pytest.mark.asyncio
    async def test_guardrail_node_escalates_ped_applicant_while_approved(self) -> None:
        """Clean draft with PED: approved is True, but escalation is True (AGENTS.md rule 4)."""
        state = create_initial_state(session_id="test_guardrail_003")
        state["user_profile"] = {"age": 42, "pre_existing_conditions": True}
        state["draft_output"] = _make_clean_draft_output()
        state["hidden_clauses"] = _make_clean_hidden_clauses()

        result = await guardrail_node(state)

        assert result["approved"] is True
        assert result["escalation"] is True
        assert "pre-existing health condition" in cast(str, result["escalation_reason"])
        assert "output" not in result


def _make_terms_db_session() -> MagicMock:
    """Mock DB session returning an active policy terms and doc row."""
    terms = MagicMock()
    terms.entry_age_min = 18
    terms.entry_age_max = 65
    terms.waiting_period_days_preexisting = 1095
    terms.sum_insured_min = 500000
    terms.sum_insured_max = 10000000
    terms.exclusions_json = ["Cosmetic surgery"]
    terms.premium_rate_table_json = {"base_5L": {"age_18_35": 8200}}
    terms.effective_date = "2024-01-01"

    doc = MagicMock()
    doc.insurer = "HDFC ERGO"
    doc.product_name = "Optima Secure"

    mock_result = MagicMock()
    mock_result.all.return_value = [(terms, doc)]
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    return mock_session


class TestGuardrailGraphIntegration:
    """Integration test verifying LangGraph pipeline executes through Stage 4."""

    @pytest.mark.asyncio
    async def test_graph_executes_with_policies_passes_guardrail_without_escalation(self) -> None:
        """Active policies and a young healthy profile pass guardrail without escalation."""
        with (
            patch(
                "app.graph.nodes.needs_intake.llm_call",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        content='{"age":28,"city_tier":"tier_1","dependents":0,'
                        '"pre_existing_conditions":false}'
                    )
                ),
            ),
            patch(
                "app.graph.nodes.intent_router.llm_call",
                new=AsyncMock(
                    return_value=SimpleNamespace(content='{"intent":"health"}')
                ),
            ),
            patch(
                "app.graph.nodes.compare_verify.AsyncSessionLocal",
                side_effect=_make_terms_db_session,
            ),
            patch(
                "app.graph.nodes.explanation_report.llm_call",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        content=(
                            '{"sentences":[{"text":"Sourced policy details are available.",'
                            '"evidence_ids":["E1"]}]}'
                        )
                    )
                ),
            ),
            # This suite verifies Stage 4 behavior; Postgres persistence is
            # covered independently and live against the Compose database.
            patch(
                "app.graph.build_graph.persist_memory_node",
                new=AsyncMock(return_value={"decision_trace_persisted": True}),
            ),
        ):
            graph = build_graph()
            state = create_initial_state(
                session_id="test_integration_stage4_001",
                user_message=(
                    "I am 28, live in Mumbai, no dependents, healthy, no pre-existing conditions"
                ),
            )

            config: RunnableConfig = {"configurable": {"thread_id": "test_integration_stage4_001"}}
            final_state = await graph.ainvoke(state, config=config)

            # Assert Stage 4 guardrail executed and populated SessionState keys
            assert "approved" in final_state
            assert "escalation" in final_state
            assert "guardrail_notes" in final_state
            assert isinstance(final_state["guardrail_notes"], list)
            assert len(final_state["guardrail_notes"]) > 0

            # Clean profile with policies evaluated: approved and not escalated
            assert final_state["approved"] is True
            assert final_state["escalation"] is False
            assert final_state["escalation_reason"] is None

            # Stage 5 runs before the delivery gate and writes the sourced report.
            assert final_state["output"]["report_status"] in {
                "ready",
                "insufficient_verified_evidence",
            }

    @pytest.mark.asyncio
    async def test_graph_executes_empty_db_triggers_low_confidence_escalation(self) -> None:
        """Zero policies from the terms DB trigger low-confidence advisor escalation."""
        with (
            patch(
                "app.graph.nodes.needs_intake.llm_call",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        content='{"age":28,"city_tier":"tier_1","dependents":0,'
                        '"pre_existing_conditions":false}'
                    )
                ),
            ),
            patch(
                "app.graph.nodes.intent_router.llm_call",
                new=AsyncMock(
                    return_value=SimpleNamespace(content='{"intent":"health"}')
                ),
            ),
            patch(
                "app.graph.nodes.compare_verify.AsyncSessionLocal",
                side_effect=_make_empty_db_session,
            ),
            patch(
                "app.graph.nodes.explanation_report.llm_call",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        content=(
                            '{"sentences":[{"text":"Sourced policy details are available.",'
                            '"evidence_ids":["E1"]}]}'
                        )
                    )
                ),
            ),
            patch(
                "app.graph.build_graph.persist_memory_node",
                new=AsyncMock(return_value={"decision_trace_persisted": True}),
            ),
        ):
            graph = build_graph()
            state = create_initial_state(
                session_id="test_integration_stage4_002",
                user_message=(
                    "I am 28, live in Mumbai, no dependents, healthy, no pre-existing conditions"
                ),
            )

            config: RunnableConfig = {"configurable": {"thread_id": "test_integration_stage4_002"}}
            final_state = await graph.ainvoke(state, config=config)

            assert final_state["approved"] is True
            assert final_state["escalation"] is True
            assert "Low confidence" in cast(str, final_state.get("escalation_reason"))
            # Escalation gates delivery; it does not skip report generation.
            assert "output" in final_state
            assert final_state["delivery_hold"] is True
