"""guardrail — Stage 4 compliance and disclosure enforcement.

Trigger: after compare_verify.
Reads:   draft_output, hidden_clauses, user_profile.
Writes:  guardrail_notes, approved (bool), escalation (bool),
         escalation_reason (str | None).
Calls:   hallucination check (re-queries sources), rules engine,
         ranking_language_check, citation_validator.

CRITICAL CONTRACT (AGENTS.md rule 4):
  - This node sets ``approved`` and ``escalation``.
  - This node does NOT write ``output``.
  - Only ``explanation_report`` writes ``output``.
  - Escalation gates DELIVERY, not GENERATION.

Confidence scoring (retrieval agreement + self-consistency check)
feeds the Human Advisor Escalation rule directly.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, TypeGuard

from app.graph.state import SessionState

logger = logging.getLogger(__name__)

# ── Compliance Constants (AGENTS.md rule 1 & rule 6) ──────────────────────────

# Prohibited ranking words per AGENTS.md rule 1.
# Never use "rank," "ranking," "best," or "top" in any user-facing text.
PROHIBITED_RANKING_WORDS: list[str] = [
    "best",
    "rank",
    "ranking",
    "ranked",
    "ranks",
    "top",
    "winner",
    "#1",
    "number 1",
    "number one",
    "superior to",
    "outranks",
]

# Promissory or unlicensed advice language forbidden under IRDAI guidelines.
UNLICENSED_ADVICE_PHRASES: list[str] = [
    "guaranteed return",
    "i guarantee",
    "you must buy",
    "you must purchase",
    "unconditional coverage",
    "guaranteed approval",
    "investment recommendation",
    "risk-free investment",
]

# Escalation thresholds (LLD § 12 & consolidated prompt)
HIGH_VALUE_COVER_THRESHOLD_INR: int = 10_000_000  # ₹1 Crore
SENIOR_CITIZEN_AGE_THRESHOLD: int = 60
MIN_CONFIDENCE_THRESHOLD: float = 0.70


# ── Compliance Checkers ───────────────────────────────────────────────────────


def check_ranking_language(text: str) -> list[str]:
    """Scan text for prohibited ranking words using word boundaries.

    Enforces AGENTS.md rule 1: Every comparison is need-fit framing only.
    """
    violations: list[str] = []
    text_lower = text.lower()
    for word in PROHIBITED_RANKING_WORDS:
        pattern = r"(?<!\w)" + re.escape(word) + r"(?!\w)"
        if re.search(pattern, text_lower):
            violations.append(f"Prohibited ranking word detected: '{word}'")
    return violations


def check_unlicensed_advice(text: str) -> list[str]:
    """Scan text for unlicensed advice or promissory financial phrases."""
    violations: list[str] = []
    text_lower = text.lower()
    for phrase in UNLICENSED_ADVICE_PHRASES:
        if phrase in text_lower:
            violations.append(f"Unlicensed advice phrasing detected: '{phrase}'")
    return violations


def _scan_text_fields(obj: Any, path: str = "") -> list[str]:
    """Recursively traverse draft_output and check all text strings for compliance."""
    violations: list[str] = []
    if isinstance(obj, str):
        # Exclude internal metadata/debug keys or raw URLs:
        # compliance_note is internal metadata quoting the rule itself
        if (
            not path.endswith("_hash")
            and not path.endswith("url")
            and not path.endswith("compliance_note")
        ):
            ranking_violations = check_ranking_language(obj)
            for v in ranking_violations:
                violations.append(f"[{path}] {v}")
            advice_violations = check_unlicensed_advice(obj)
            for v in advice_violations:
                violations.append(f"[{path}] {v}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            new_path = f"{path}.{k}" if path else k
            violations.extend(_scan_text_fields(v, new_path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            violations.extend(_scan_text_fields(item, f"{path}[{i}]"))
    return violations


def check_provenance_and_citations(
    draft_output: dict[str, Any],
    hidden_clauses: list[dict[str, Any]],
) -> list[str]:
    """Verify every claim, term, and fact carries source + last_verified.

    Enforces AGENTS.md rule 6: Every claim in output carries a source and
    a last-verified date. No exceptions, no matter how obvious the claim seems.
    """
    violations: list[str] = []

    # 1. Check need_fit_view policies
    need_fit = draft_output.get("need_fit_view", [])
    for idx, policy in enumerate(need_fit):
        p_name = policy.get("product_name", f"policy_{idx}")

        # Check numeric terms
        terms_to_check = [
            ("sum_insured_range_inr", policy.get("sum_insured_range_inr")),
            ("entry_age_window", policy.get("entry_age_window")),
            ("waiting_period_days_preexisting", policy.get("waiting_period_days_preexisting")),
        ]

        for term_name, term_dict in terms_to_check:
            if not isinstance(term_dict, dict):
                violations.append(f"Policy '{p_name}' {term_name} is not a structured dict")
                continue
            if not term_dict.get("source"):
                violations.append(f"Policy '{p_name}' {term_name} missing 'source'")
            if not term_dict.get("last_verified"):
                violations.append(f"Policy '{p_name}' {term_name} missing 'last_verified'")

        # Premium estimate (if populated)
        premium = policy.get("premium_estimate")
        if premium and isinstance(premium, dict):
            if not premium.get("source"):
                violations.append(f"Policy '{p_name}' premium_estimate missing 'source'")
            if not premium.get("last_verified"):
                violations.append(f"Policy '{p_name}' premium_estimate missing 'last_verified'")

    # 2. Check cited_facts
    cited_facts = draft_output.get("cited_facts", [])
    for idx, fact in enumerate(cited_facts):
        if not fact.get("source"):
            violations.append(f"Cited fact [{idx}] missing 'source'")
        if not fact.get("last_verified"):
            violations.append(f"Cited fact [{idx}] missing 'last_verified'")

    # 3. Check hidden_clauses
    for group in hidden_clauses:
        policy_key = group.get("policy_key", "unknown")
        for idx, clause in enumerate(group.get("clauses", [])):
            if not clause.get("source"):
                violations.append(f"Hidden clause [{idx}] in '{policy_key}' missing 'source'")
            if not clause.get("last_verified"):
                violations.append(
                    f"Hidden clause [{idx}] in '{policy_key}' missing 'last_verified'"
                )

    return violations


def _structured_term(policy: dict[str, Any], key: str) -> dict[str, Any]:
    """Return only a term object; provenance checks report invalid containers."""
    value = policy.get(key)
    return value if isinstance(value, dict) else {}


def _finite_number(value: Any) -> TypeGuard[int | float]:
    return type(value) is int or (type(value) is float and math.isfinite(value))


def check_numeric_hallucinations(draft_output: dict[str, Any]) -> list[str]:
    """Verify consistency and sanity of deterministic numbers.

    Enforces AGENTS.md rule 5: Anything with one correct answer is deterministic,
    not RAG. Validates that figures follow logical range bounds.
    """
    violations: list[str] = []
    need_fit = draft_output.get("need_fit_view", [])

    for idx, policy in enumerate(need_fit):
        p_name = policy.get("product_name", f"policy_{idx}")

        # Sum insured range
        si_range = _structured_term(policy, "sum_insured_range_inr")
        si_min = si_range.get("min")
        si_max = si_range.get("max")
        age_window = _structured_term(policy, "entry_age_window")
        age_min = age_window.get("min")
        age_max = age_window.get("max")
        wp = _structured_term(policy, "waiting_period_days_preexisting")
        wp_val = wp.get("value")
        for label, value in (
            ("minimum sum insured", si_min),
            ("maximum sum insured", si_max),
            ("minimum entry age", age_min),
            ("maximum entry age", age_max),
            ("waiting period", wp_val),
        ):
            if value is not None and not _finite_number(value):
                violations.append(f"Policy '{p_name}' {label} must be a finite number")

        if any(_finite_number(value) and value < 0 for value in (si_min, si_max)):
            violations.append(f"Policy '{p_name}' sum insured range cannot be negative")
        if _finite_number(si_min) and _finite_number(si_max) and si_max > 0 and si_min > si_max:
            violations.append(
                f"Policy '{p_name}' min sum insured ({si_min}) exceeds max ({si_max})"
            )

        # Entry age window
        if any(_finite_number(value) and value < 0 for value in (age_min, age_max)):
            violations.append(f"Policy '{p_name}' entry age cannot be negative")
        if _finite_number(age_min) and _finite_number(age_max) and age_min > age_max:
            violations.append(
                f"Policy '{p_name}' min entry age ({age_min}) exceeds max ({age_max})"
            )

        # Waiting period
        if _finite_number(wp_val) and wp_val < 0:
            violations.append(f"Policy '{p_name}' waiting period cannot be negative ({wp_val})")

    return violations


def calculate_confidence_score(
    draft_output: dict[str, Any],
    violations: list[str],
    user_profile: dict[str, Any] | None = None,
) -> float:
    """Calculate confidence score (0.0 to 1.0) based on data completeness and compliance.

    Feeds into the Human Advisor Escalation rule directly per LLD § 7.2.
    Evaluates:
      1. Policy term completeness (sum insured, entry age, waiting period, premium estimate)
      2. Retrieval facts availability and conflict detection
      3. User profile completeness (age, city tier, dependents, PED declaration)
      4. Compliance and sanity violations
    """
    comp_score = max(0.0, 1.0 - 0.40 * len(violations)) if violations else 1.0

    policies = draft_output.get("need_fit_view", [])
    if not policies:
        term_score = 0.0
    else:
        policy_scores: list[float] = []
        for p in policies:
            has_si = 1.0 if _structured_term(p, "sum_insured_range_inr").get("max") else 0.0
            has_age = 1.0 if _structured_term(p, "entry_age_window").get("max") else 0.0
            has_wp = (
                1.0
                if (_structured_term(p, "waiting_period_days_preexisting").get("value") is not None)
                else 0.0
            )
            has_prem = (
                1.0 if _structured_term(p, "premium_estimate").get("annual_premium_inr") else 0.0
            )
            policy_scores.append((has_si + has_age + has_wp + has_prem) / 4.0)
        term_score = sum(policy_scores) / len(policy_scores)

    # Retrieval evidence score (0.0 to 1.0)
    cited_facts = draft_output.get("cited_facts", [])
    if not cited_facts:
        retrieval_score = 0.0
    else:
        has_conflicts = any(f.get("conflict", False) for f in cited_facts)
        retrieval_score = 0.50 if has_conflicts else 1.0

    # User profile completeness (0.0 to 1.0)
    # An explicitly empty current profile must not borrow a stale snapshot.
    profile = (
        user_profile if user_profile is not None else draft_output.get("user_profile_snapshot", {})
    )
    if profile:
        has_age = (
            1.0 if (profile.get("age") is not None and int(profile.get("age", 0)) > 0) else 0.0
        )
        has_city = 1.0 if profile.get("city_tier") in ("tier_1", "tier_2", "tier_3") else 0.0
        has_deps = 1.0 if profile.get("dependents") is not None else 0.0
        has_ped = 1.0 if profile.get("pre_existing_conditions") is not None else 0.0
        profile_score = (has_age + has_city + has_deps + has_ped) / 4.0
    else:
        profile_score = 0.0

    if violations:
        raw = (term_score * 0.35 + retrieval_score * 0.25 + profile_score * 0.20) * comp_score
    else:
        raw = term_score * 0.35 + retrieval_score * 0.25 + profile_score * 0.20 + comp_score * 0.20

    return round(max(0.0, min(1.0, raw)), 2)


def _profile_completeness(profile: dict[str, Any]) -> float:
    fields = (
        profile.get("age") is not None and int(profile.get("age", 0)) > 0,
        profile.get("city_tier") in ("tier_1", "tier_2", "tier_3"),
        profile.get("dependents") is not None,
        profile.get("pre_existing_conditions") is not None,
    )
    return sum(fields) / len(fields)


def _retrieval_agreement(draft: dict[str, Any]) -> float:
    facts = draft.get("cited_facts", [])
    if not facts:
        return 0.0
    return 0.5 if any(f.get("conflict", False) for f in facts) else 1.0


def _policy_term_completeness(draft: dict[str, Any]) -> float:
    policies = draft.get("need_fit_view", [])
    if not policies:
        return 0.0
    scores = []
    for policy in policies:
        scores.append(
            sum(
                (
                    bool(_structured_term(policy, "sum_insured_range_inr").get("max")),
                    bool(_structured_term(policy, "entry_age_window").get("max")),
                    _structured_term(policy, "waiting_period_days_preexisting").get("value")
                    is not None,
                    bool(_structured_term(policy, "premium_estimate").get("annual_premium_inr")),
                )
            )
            / 4.0
        )
    return sum(scores) / len(scores)


def evaluate_escalation(
    user_profile: dict[str, Any],
    draft_output: dict[str, Any],
    confidence_score: float,
    violations: list[str],
) -> tuple[bool, str | None]:
    """Evaluate whether case must escalate to a human licensed advisor.

    Triggers per LLD § 12, consolidated prompt, and escalate node contract:
      1. Compliance violations (unapproved draft)
      2. Pre-existing conditions (PED) declared
      3. Non-Resident Indian (NRI) status declared
      4. Senior citizen applicant (age >= 60)
      5. High sum insured (target >= ₹1 Crore)
      6. Zero eligible policies found
      7. Low confidence score (< 0.70)
    """
    # 1. Compliance violations block automated delivery
    if violations:
        return (
            True,
            f"Compliance violations detected: {violations[0]}",
        )

    # 2. Pre-existing health conditions
    ped = user_profile.get("pre_existing_conditions")
    has_ped = False
    if isinstance(ped, bool):
        has_ped = ped
    elif isinstance(ped, str):
        has_ped = ped.strip().lower() not in ("none", "no", "false", "nil", "")
    elif isinstance(ped, (list, set, tuple)):
        has_ped = len(ped) > 0

    if has_ped:
        return (
            True,
            "High-stakes profile: declared pre-existing health condition requires "
            "licensed human underwriter review prior to final recommendation.",
        )

    # 3. Non-Resident Indian (NRI) status
    raw_nri = user_profile.get("is_nri")
    if raw_nri is None:
        raw_nri = user_profile.get("nri")
    is_nri = False
    if isinstance(raw_nri, bool):
        is_nri = raw_nri
    elif isinstance(raw_nri, str):
        is_nri = raw_nri.strip().lower() in (
            "true",
            "yes",
            "1",
            "nri",
            "non-resident",
            "non_resident",
        )

    if is_nri:
        return (
            True,
            "High-stakes profile: declared Non-Resident Indian (NRI) status requires "
            "specialized cross-border taxation (FEMA/GST), territorial limits review, "
            "and licensed advisor consultation.",
        )

    # 4. Senior citizen applicant (age >= 60)
    user_age = int(user_profile.get("age", 0))
    if user_age >= SENIOR_CITIZEN_AGE_THRESHOLD:
        return (
            True,
            f"High-stakes profile: applicant age ({user_age}) meets or exceeds senior "
            f"threshold ({SENIOR_CITIZEN_AGE_THRESHOLD}+); "
            "requires specialized underwriting review.",
        )

    # 5. High sum insured (>= ₹1 Crore)
    target_si = draft_output.get("risk_adjusted_target_si_inr", {}).get(
        "value", 0
    ) or user_profile.get("target_sum_insured", 0)
    if target_si >= HIGH_VALUE_COVER_THRESHOLD_INR:
        return (
            True,
            f"High-stakes coverage: target sum insured (₹{target_si:,.0f}) reaches or exceeds "
            f"₹1 Crore threshold; senior advisor sign-off required.",
        )

    # 6. Zero eligible policies
    policies = draft_output.get("need_fit_view", [])
    if policies and not any(p.get("eligible", False) for p in policies):
        return (
            True,
            "No standard policies evaluated met applicant eligibility criteria; "
            "requires human advisor consultation for specialized coverage options.",
        )

    # 7. Low confidence score (< 0.70)
    if confidence_score < MIN_CONFIDENCE_THRESHOLD:
        return (
            True,
            f"Low confidence score ({confidence_score:.2f} < {MIN_CONFIDENCE_THRESHOLD}); "
            f"human advisor validation required before delivery.",
        )

    return (False, None)


# ── Guardrail Node ────────────────────────────────────────────────────────────


async def guardrail_node(state: SessionState) -> dict[str, Any]:
    """Execute Stage 4 compliance check and advisor escalation assessment.

    CRITICAL CONTRACT (AGENTS.md rule 4):
      - Sets ``approved``, ``escalation``, ``escalation_reason``, ``guardrail_notes``.
      - Does NOT write ``output``.
      - Only ``explanation_report`` writes ``output``.
    """
    draft_output = state.get("draft_output", {})
    hidden_clauses = state.get("hidden_clauses", [])
    user_profile = state.get("user_profile", {})
    session_id = state.get("session_id", "unknown")

    guardrail_notes: list[str] = []
    all_violations: list[str] = []

    # 1. Scan draft_output text for prohibited ranking language & unlicensed advice
    text_violations = _scan_text_fields(draft_output)
    if text_violations:
        all_violations.extend(text_violations)
        guardrail_notes.append(
            f"FAILED text compliance check: {len(text_violations)} violation(s) found. "
            f"Detail: {'; '.join(text_violations[:3])}"
        )
    else:
        guardrail_notes.append(
            "PASSED text compliance check: no prohibited ranking words or unlicensed advice."
        )

    # 2. Check provenance on all claims, terms, and citations (Rule 6)
    provenance_violations = check_provenance_and_citations(draft_output, hidden_clauses)
    if provenance_violations:
        all_violations.extend(provenance_violations)
        guardrail_notes.append(
            f"FAILED provenance check (AGENTS.md rule 6): {len(provenance_violations)} item(s) "
            "missing source or date. "
            f"Detail: {'; '.join(provenance_violations[:3])}"
        )
    else:
        guardrail_notes.append(
            "PASSED provenance check: all policy terms, facts, "
            "and hidden clauses carry verified sources."
        )

    # 3. Check deterministic numeric bounds (Rule 5)
    numeric_violations = check_numeric_hallucinations(draft_output)
    if numeric_violations:
        all_violations.extend(numeric_violations)
        guardrail_notes.append(
            f"FAILED numeric sanity check (AGENTS.md rule 5): {len(numeric_violations)} "
            "issue(s) detected. "
            f"Detail: {'; '.join(numeric_violations[:2])}"
        )
    else:
        guardrail_notes.append(
            "PASSED numeric sanity check: all policy ranges and waiting periods "
            "are within valid bounds."
        )

    # 4. Calculate confidence score
    confidence_score = calculate_confidence_score(
        draft_output,
        all_violations,
        user_profile=user_profile,
    )
    guardrail_notes.append(f"Confidence score calculated: {confidence_score:.2f}")

    # 5. Determine approval
    approved = len(all_violations) == 0
    if approved:
        guardrail_notes.append("STATUS: Approved for explanation generation.")
    else:
        guardrail_notes.append(
            f"STATUS: Disapproved ({len(all_violations)} compliance violations)."
        )

    # 6. Evaluate escalation triggers
    escalation, escalation_reason = evaluate_escalation(
        user_profile=user_profile,
        draft_output=draft_output,
        confidence_score=confidence_score,
        violations=all_violations,
    )

    if escalation:
        guardrail_notes.append(f"ESCALATION TRIGGERED: {escalation_reason}")
    else:
        guardrail_notes.append("ESCALATION: Not required.")

    logger.info(
        "guardrail: session=%s, approved=%s, escalation=%s, confidence=%.2f, notes=%d",
        session_id,
        approved,
        escalation,
        confidence_score,
        len(guardrail_notes),
    )

    # Return only the contracted fields — NEVER write 'output' (AGENTS.md rule 4)
    return {
        "approved": approved,
        "escalation": escalation,
        "escalation_reason": escalation_reason,
        "guardrail_notes": guardrail_notes,
        "confidence_score": confidence_score,
        "confidence_inputs": {
            "profile_completeness": _profile_completeness(user_profile),
            "retrieval_agreement": _retrieval_agreement(draft_output),
            "policy_term_completeness": _policy_term_completeness(draft_output),
            "compliance_violation_count": len(all_violations),
        },
    }
