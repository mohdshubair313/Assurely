"""compare_verify — Stage 3 fan-in: cross-checks and merges domain outputs.

Trigger: after ALL Stage 2 branches complete (fan-in join — not a race).
Reads:   retrieved_facts, calculator_outputs, user_profile.
Writes:  draft_output, hidden_clauses, transparency_scores.

Architecture (LLD § 7.2):
- Deterministic `policy_terms` table lookups for all numbers (rule 5).
  Eligibility, sum-insured limits, exclusions, effective dates, and premium
  figures ALWAYS come from the DB — never from RAG or LLM invention.
- RAG (`retrieved_facts`) feeds clause-wording context only.
- Hidden Clause Detector (deterministic): flags exclusions, waiting periods,
  sub-limits, and room-rent caps that directly affect the user's stated profile.
- Transparency Scorer (deterministic 0–100): fewer hidden trip-wires that
  match the user's profile = higher openness score.
- Need-fit summary written to draft_output: never ranking language (rule 1).
- Every claim in draft_output carries source + last_verified (rule 6).

Key rule (AGENTS.md rule 5): eligibility, exclusions, sum-insured limits,
premium figures, effective dates → ``policy_terms`` table lookups.
RAG is used here ONLY for clause wording to explain in plain language.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.graph.state import SessionState
from app.models.db.policy_document import PolicyDocument
from app.models.db.policy_terms import PolicyTerms

logger = logging.getLogger(__name__)

# ── source / provenance label used on every deterministic claim ──────────────
_DB_SOURCE = "policy_terms table (InsuranceAI DB)"
_LAST_VERIFIED = "2024-01-01"  # date of seed data; must be updated when real docs are loaded


# ── Hidden Clause Detector ────────────────────────────────────────────────────

# Keywords in exclusion strings that are directly relevant to common user needs.
# Grouped by profile attribute that triggers relevance.
_EXCLUSION_TRIGGERS: list[tuple[str, list[str]]] = [
    # (profile attribute or condition → list of exclusion text substrings to flag)
    ("pre_existing_conditions", ["pre-existing", "pre existing", "preexisting", "waiting period"]),
    ("maternity", ["maternity", "obstetric", "pregnancy"]),
    ("obesity", ["obesity", "weight control"]),
    ("alcohol", ["alcohol", "substance abuse", "drug or substance"]),
    ("congenital", ["congenital"]),
    ("dental", ["dental"]),
    ("cosmetic", ["cosmetic", "plastic surgery", "aesthetic"]),
    ("adventure_sports", ["hazardous", "adventure sports"]),
    ("stem_cell", ["stem cell"]),
    ("experimental", ["experimental", "unproven"]),
    ("rehabilitation", ["rehabilitation", "respite care"]),
]

# Room-rent sub-limit patterns (phrases that indicate a cap).
_ROOM_RENT_KEYWORDS = ["room rent", "room-rent", "single private room", "shared room", "ward"]


def _detect_hidden_clauses(
    terms: PolicyTerms,
    doc: PolicyDocument,
    user_profile: dict[str, Any],
    retrieved_facts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return a list of flagged fine-print items for this policy.

    Each flagged item is a dict with:
        clause, severity ("high" | "medium" | "low"), reason, source, last_verified.

    Severity logic:
        high   — exclusion directly matches a stated user health condition or
                 eligibility boundary violation (age outside entry window).
        medium — exclusion matches a plausible user need based on profile (PED waiting period).
        low    — general exclusion or sub-limit that applies to most users.
    """
    flagged: list[dict[str, Any]] = []
    exclusions: list[str] = list(terms.exclusions_json or [])

    # 1. Eligibility check — age boundary (deterministic DB lookup)
    user_age: int = int(user_profile.get("age", 0))
    if user_age and terms.entry_age_min and user_age < terms.entry_age_min:
        flagged.append(
            {
                "clause": f"Entry age minimum is {terms.entry_age_min} years; user is {user_age}",
                "severity": "high",
                "reason": "User does not meet minimum entry age for this policy.",
                "source": _DB_SOURCE,
                "last_verified": _LAST_VERIFIED,
            }
        )
    if user_age and terms.entry_age_max and user_age > terms.entry_age_max:
        flagged.append(
            {
                "clause": f"Entry age maximum is {terms.entry_age_max} years; user is {user_age}",
                "severity": "high",
                "reason": "User exceeds maximum entry age for this policy.",
                "source": _DB_SOURCE,
                "last_verified": _LAST_VERIFIED,
            }
        )

    # 2. Pre-existing disease waiting period (always flag if user has PED)
    has_ped = bool(user_profile.get("pre_existing_conditions"))
    if has_ped and terms.waiting_period_days_preexisting:
        months = math.ceil(terms.waiting_period_days_preexisting / 30)
        flagged.append(
            {
                "clause": (
                    "Pre-existing disease waiting period: "
                    f"{terms.waiting_period_days_preexisting} days ({months} months)"
                ),
                "severity": "high",
                "reason": (
                    "User has declared pre-existing conditions. Coverage for those "
                    f"conditions will not apply for {months} months from policy inception."
                ),
                "source": _DB_SOURCE,
                "last_verified": _LAST_VERIFIED,
            }
        )
    elif terms.waiting_period_days_preexisting:
        # Flag even without declared PED — medium severity
        months = math.ceil(terms.waiting_period_days_preexisting / 30)
        flagged.append(
            {
                "clause": f"Pre-existing disease waiting period: {months} months",
                "severity": "medium",
                "reason": "Applies to any pre-existing conditions diagnosed before policy start.",
                "source": _DB_SOURCE,
                "last_verified": _LAST_VERIFIED,
            }
        )

    # 3. Exclusion string matching against profile signals
    profile_signals: set[str] = set()
    if has_ped:
        profile_signals.add("pre_existing_conditions")
    for attr in (
        "maternity",
        "obesity",
        "alcohol",
        "congenital",
        "dental",
        "cosmetic",
        "adventure_sports",
        "stem_cell",
        "experimental",
        "rehabilitation",
    ):
        if user_profile.get(attr):
            profile_signals.add(attr)

    for exclusion_text in exclusions:
        lower = exclusion_text.lower()
        matched_attr: str | None = None
        for attr, keywords in _EXCLUSION_TRIGGERS:
            if any(kw in lower for kw in keywords):
                matched_attr = attr
                break
        if matched_attr is None:
            # Unknown/generic exclusion — still flag at low severity
            flagged.append(
                {
                    "clause": exclusion_text,
                    "severity": "low",
                    "reason": "Standard policy exclusion. Review whether it affects your use case.",
                    "source": f"{doc.insurer} – {doc.product_name} policy wordings",
                    "last_verified": _LAST_VERIFIED,
                }
            )
        else:
            severity = "high" if matched_attr in profile_signals else "low"
            flagged.append(
                {
                    "clause": exclusion_text,
                    "severity": severity,
                    "reason": (
                        f"Directly relevant to user's profile ({matched_attr.replace('_', ' ')})."
                        if matched_attr in profile_signals
                        else "Policy exclusion — applies under specific circumstances."
                    ),
                    "source": f"{doc.insurer} – {doc.product_name} policy wordings",
                    "last_verified": _LAST_VERIFIED,
                }
            )

    # 4. Room-rent sub-limit detection from retrieved RAG facts
    for fact in retrieved_facts:
        claim_text: str = str(fact.get("claim", "")).lower()
        if any(kw in claim_text for kw in _ROOM_RENT_KEYWORDS):
            flagged.append(
                {
                    "clause": fact.get("claim", ""),
                    "severity": "medium",
                    "reason": (
                        "Room-rent sub-limits can cause proportionate deductions across all "
                        "in-hospital bills (anaesthesia, medicines, doctor fees) even if the "
                        "overall sum insured is not exhausted."
                    ),
                    "source": fact.get("source", ""),
                    "last_verified": fact.get("last_verified", ""),
                }
            )

    return flagged


# ── Transparency Scorer ───────────────────────────────────────────────────────


def _compute_transparency_score(
    hidden_clauses: list[dict[str, Any]],
    terms: PolicyTerms,
    user_profile: dict[str, Any],
) -> dict[str, Any]:
    """Score policy transparency on a 0–100 scale.

    Scoring philosophy:
        Start at 100. Deduct points for hidden trip-wires that affect this
        particular user. Reward for broad age eligibility, lower waiting periods,
        and high sum-insured ceiling. This is about disclosure openness, NOT
        about which policy is "better" (AGENTS.md rule 1).

    Deductions:
        -25 per high-severity hidden clause
            (eligibility block, PED waiting, high-relevance exclusion)
        -10 per medium-severity hidden clause
        -3  per low-severity hidden clause
    Bonuses:
        +5  if entry_age_max >= 99 (lifetime renewability signal)
        +5  if sum_insured_max >= 2_00_00_000 (2 crore — high ceiling)
        +5  if waiting_period_days_preexisting <= 730 (2-year or less PED wait)
    """
    score: float = 100.0

    for clause in hidden_clauses:
        sev = clause.get("severity", "low")
        if sev == "high":
            score -= 25
        elif sev == "medium":
            score -= 10
        else:
            score -= 3

    # Positive signals
    if terms.entry_age_max is not None and terms.entry_age_max >= 99:
        score += 5
    if terms.sum_insured_max is not None and terms.sum_insured_max >= Decimal("20000000"):
        score += 5
    if (
        terms.waiting_period_days_preexisting is not None
        and terms.waiting_period_days_preexisting <= 730
    ):
        score += 5

    return {
        "score": max(0, min(100, round(score))),
        "note": (
            "Transparency score measures disclosure openness for this user's profile — "
            "higher means fewer undisclosed trip-wires. It is not an overall quality rating."
        ),
    }


# ── Premium lookup (deterministic) ────────────────────────────────────────────


def _lookup_premium(
    rate_table: dict[str, Any] | None,
    target_sum_insured_inr: float,
    user_age: int,
) -> dict[str, Any] | None:
    """Look up the nearest premium bracket deterministically.

    Returns a dict with {bracket, annual_premium_inr, source, last_verified}
    or None if the table is empty / brackets don't cover the age.
    """
    if not rate_table or not user_age:
        return None

    # Map age to bracket key
    if user_age <= 35:
        age_key = "age_18_35"
    elif user_age <= 45:
        age_key = "age_36_45"
    elif user_age <= 55:
        age_key = "age_46_55"
    elif user_age <= 65:
        age_key = "age_56_65"
    else:
        return None  # outside seeded table range

    # Map target sum insured to nearest bracket
    si_crore = target_sum_insured_inr / 100_000  # convert to lakhs
    if si_crore <= 7.5:
        si_key = "base_5L"
        bracket_label = "₹5 Lakh"
    elif si_crore <= 17.5:
        si_key = "base_10L"
        bracket_label = "₹10 Lakh"
    else:
        si_key = "base_25L"
        bracket_label = "₹25 Lakh"

    bracket = rate_table.get(si_key, {})
    premium = bracket.get(age_key)
    if premium is None:
        return None

    return {
        "bracket": bracket_label,
        "annual_premium_inr": int(premium),
        "source": _DB_SOURCE,
        "last_verified": _LAST_VERIFIED,
        "note": (
            "Plausible seed figure — must be verified against real insurer rate cards "
            "before showing to users."
        ),
    }


# ── Eligibility helper ────────────────────────────────────────────────────────


def _check_eligibility(terms: PolicyTerms, user_profile: dict[str, Any]) -> bool:
    """True if the user's age falls within the policy's entry window."""
    user_age = int(user_profile.get("age", 0))
    if not user_age:
        return True  # cannot determine — assume eligible until profile complete
    if terms.entry_age_min and user_age < terms.entry_age_min:
        return False
    return not (terms.entry_age_max and user_age > terms.entry_age_max)


# ── Node entry point ──────────────────────────────────────────────────────────


async def compare_verify_node(state: SessionState) -> dict[str, Any]:
    """Execute the compare_verify node — Stage 3 fan-in.

    Reads retrieved_facts (Stage 2 RAG) and calculator_outputs (Stage 2 risk
    analysis). Performs deterministic policy_terms lookups. Runs hidden clause
    detection and transparency scoring. Writes draft_output, hidden_clauses,
    and transparency_scores.

    AGENTS.md rule 5: all numbers come from DB lookups, not LLM invention.
    AGENTS.md rule 1: no ranking / "best" / "top" language anywhere in output.
    AGENTS.md rule 6: every claim carries source + last_verified.
    """
    session_id = state.get("session_id", "unknown")
    user_profile: dict[str, Any] = state.get("user_profile", {})
    retrieved_facts: list[dict[str, Any]] = state.get("retrieved_facts", [])
    calculator_outputs: dict[str, Any] = state.get("calculator_outputs", {})

    # Pull target sum insured from risk_analysis output (deterministic calc)
    risk_output: dict[str, Any] = calculator_outputs.get("risk_analysis", {})
    target_si: float = float(risk_output.get("risk_adjusted_sum_insured_inr", 1_000_000))
    user_age: int = int(user_profile.get("age", 0))

    logger.info(
        "compare_verify: session=%s, target_SI=₹%s, age=%s, facts=%d",
        session_id,
        f"{target_si:,.0f}",
        user_age,
        len(retrieved_facts),
    )

    # ── Deterministic DB lookups (AGENTS.md rule 5) ──────────────────────────
    policy_entries: list[dict[str, Any]] = []
    all_hidden_clauses: dict[str, list[dict[str, Any]]] = {}
    all_transparency_scores: dict[str, dict[str, Any]] = {}

    async with AsyncSessionLocal() as db_session:
        stmt = (
            select(PolicyTerms, PolicyDocument)
            .join(PolicyDocument, PolicyTerms.policy_document_id == PolicyDocument.id)
            .where(PolicyTerms.expiry_date.is_(None))  # active terms only
            .order_by(PolicyDocument.insurer)
        )
        result = await db_session.execute(stmt)
        rows: list[tuple[PolicyTerms, PolicyDocument]] = [
            cast(tuple[PolicyTerms, PolicyDocument], r) for r in result.all()
        ]

    if not rows:
        logger.warning("compare_verify: no active policy_terms rows found in DB")

    for terms, doc in rows:
        policy_key = f"{doc.insurer}|{doc.product_name}"

        # Eligibility
        eligible = _check_eligibility(terms, user_profile)

        # Hidden clause detection
        clauses = _detect_hidden_clauses(terms, doc, user_profile, retrieved_facts)
        all_hidden_clauses[policy_key] = clauses

        # Transparency score
        ts = _compute_transparency_score(clauses, terms, user_profile)
        all_transparency_scores[policy_key] = ts

        # Premium lookup (deterministic)
        premium_info = _lookup_premium(
            rate_table=dict(terms.premium_rate_table_json or {}),
            target_sum_insured_inr=target_si,
            user_age=user_age,
        )

        # Fit summary — need-fit framing, never ranking (AGENTS.md rule 1)
        high_clauses = [c for c in clauses if c["severity"] == "high"]
        medium_clauses = [c for c in clauses if c["severity"] == "medium"]

        fit_notes: list[str] = []
        if not eligible:
            fit_notes.append("User's age falls outside this policy's entry window.")
        if high_clauses:
            fit_notes.append(
                f"{len(high_clauses)} clause(s) directly affect user's stated profile "
                f"(pre-existing conditions, eligibility)."
            )
        if medium_clauses:
            fit_notes.append(
                f"{len(medium_clauses)} clause(s) may affect user depending on future needs "
                f"(waiting periods, sub-limits)."
            )
        if not fit_notes:
            fit_notes.append("No clauses directly conflict with stated profile at this time.")

        entry: dict[str, Any] = {
            "insurer": doc.insurer,
            "product_name": doc.product_name,
            "eligible": eligible,
            "sum_insured_range_inr": {
                "min": int(terms.sum_insured_min or 0),
                "max": int(terms.sum_insured_max or 0),
                "source": _DB_SOURCE,
                "last_verified": _LAST_VERIFIED,
            },
            "entry_age_window": {
                "min": terms.entry_age_min,
                "max": terms.entry_age_max,
                "source": _DB_SOURCE,
                "last_verified": _LAST_VERIFIED,
            },
            "waiting_period_days_preexisting": {
                "value": terms.waiting_period_days_preexisting,
                "source": _DB_SOURCE,
                "last_verified": _LAST_VERIFIED,
            },
            "effective_date": str(terms.effective_date),
            "premium_estimate": premium_info,
            "transparency_score": ts["score"],
            "hidden_clause_count": {
                "high": len(high_clauses),
                "medium": len(medium_clauses),
                "low": len([c for c in clauses if c["severity"] == "low"]),
            },
            "fit_notes": fit_notes,
            # Need-fit framing: how this policy aligns with user's stated needs.
            # NO "best", "rank", "top" language (AGENTS.md rule 1).
        }
        policy_entries.append(entry)

    # ── RAG fact cross-references ─────────────────────────────────────────────
    # Pass verified clause wordings through; they carry their own source (rule 6).
    cited_facts = [
        {
            "claim": f.get("claim", ""),
            "source": f.get("source", ""),
            "url": f.get("url", ""),
            "retrieved_at": f.get("retrieved_at", ""),
            "last_verified": f.get("last_verified", _LAST_VERIFIED),
            "conflict": f.get("conflict", False),
        }
        for f in retrieved_facts
    ]

    # ── Compose draft_output ──────────────────────────────────────────────────
    draft_output: dict[str, Any] = {
        "stage": "compare_verify",
        "generated_at": datetime.now(UTC).isoformat(),
        "user_profile_snapshot": {
            "age": user_profile.get("age"),
            "city_tier": user_profile.get("city_tier"),
            "dependents": user_profile.get("dependents"),
            "pre_existing_conditions": user_profile.get("pre_existing_conditions"),
        },
        "risk_adjusted_target_si_inr": {
            "value": target_si,
            "source": "app.calculators.risk_profile (deterministic)",
            "last_verified": datetime.now(UTC).date().isoformat(),
        },
        # Need-fit view — not a ranking.
        # explanation_report (Stage 5) will use this to produce prose for the user.
        "need_fit_view": policy_entries,
        "cited_facts": cited_facts,
        "total_policies_evaluated": len(policy_entries),
        "compliance_note": (
            "This output uses need-fit framing only. "
            "No policy is ordered, endorsed, or described as 'best' or 'top' "
            "(AGENTS.md rule 1). All numeric figures are from policy_terms table "
            "lookups (AGENTS.md rule 5). Every claim carries source + last_verified "
            "(AGENTS.md rule 6). Seed data is plausible but unverified — "
            "must be audited against real policy documents before production use "
            "(PROGRESS.md deviation #5)."
        ),
    }

    logger.info(
        "compare_verify: session=%s, evaluated %d policies, "
        "total hidden clauses: high=%d medium=%d low=%d",
        session_id,
        len(policy_entries),
        sum(e["hidden_clause_count"]["high"] for e in policy_entries),
        sum(e["hidden_clause_count"]["medium"] for e in policy_entries),
        sum(e["hidden_clause_count"]["low"] for e in policy_entries),
    )

    return {
        "draft_output": draft_output,
        "hidden_clauses": [{"policy_key": k, "clauses": v} for k, v in all_hidden_clauses.items()],
        "transparency_scores": {k: v["score"] for k, v in all_transparency_scores.items()},
    }
