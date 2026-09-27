"""SessionState — the LangGraph shared state schema (LLD § 7.1).

Defines the TypedDict that flows through every node in the graph.
All routing decisions are made by inspecting fields on this state
(``intent``, ``escalation``, ``approved``, ``missing_fields``),
never by asking an LLM what should happen next (AGENTS.md rule 2).

Fields:
    session_id          — unique session identifier
    messages            — conversation history turns with role and content
    user_profile        — age, dependents, income, city_tier, health_flags, etc.
    consent             — what the user has agreed to, timestamped
    intent              — "life" | "health" | "unclear" | None
    missing_fields      — list of profile fields still needed
    calculator_outputs  — human life value, ideal health cover, etc.
    retrieved_facts     — [{claim, source, url, retrieved_at}, ...]
    hidden_clauses      — flagged fine print from Compare & Verify
    transparency_scores — wording-openness scores per policy
    draft_output        — intermediate output from compare_verify
    guardrail_notes     — compliance annotations from the guardrail node
    approved            — set by guardrail; explanation_report only ships if True
    escalation          — whether human advisor review is required
    escalation_reason   — why escalation was triggered
    delivery_hold       — fail-closed API delivery gate, written by escalate
    advisor_notification — queue receipt; acknowledgement is not advisor sign-off
    output              — written ONLY by explanation_report, never by guardrail
    target_language     — detected on first turn: "hi", "en", or "hi-en-mixed"
"""

from __future__ import annotations

from typing import Any, TypedDict


class SessionState(TypedDict, total=False):
    """Shared state dictionary passed across all nodes in the LangGraph."""

    session_id: str
    user_id: str | None
    messages: list[dict[str, Any]]
    user_profile: dict[str, Any]
    consent: dict[str, Any]
    intent: str | None
    missing_fields: list[str]
    calculator_outputs: dict[str, Any]
    retrieved_facts: list[dict[str, Any]]
    hidden_clauses: list[dict[str, Any]]
    transparency_scores: dict[str, Any]
    draft_output: dict[str, Any]
    guardrail_notes: list[str]
    confidence_score: float | None
    confidence_inputs: dict[str, Any]
    approved: bool
    escalation: bool
    escalation_reason: str | None
    delivery_hold: bool
    advisor_notification: dict[str, Any]
    output: dict[str, Any]
    target_language: str


def create_initial_state(
    session_id: str,
    user_message: str | None = None,
    consent: dict[str, Any] | None = None,
    target_language: str = "en",
    user_id: str | None = None,
    user_profile: dict[str, Any] | None = None,
) -> SessionState:
    """Instantiate a clean initial state with documented defaults."""
    messages: list[dict[str, Any]] = []
    if user_message:
        messages.append({"role": "user", "content": user_message})

    return SessionState(
        session_id=session_id,
        user_id=user_id,
        messages=messages,
        user_profile=dict(user_profile or {}),
        consent=consent or {"granted": False, "scopes": []},
        intent=None,
        missing_fields=["age", "city_tier", "dependents", "pre_existing_conditions"],
        calculator_outputs={},
        retrieved_facts=[],
        hidden_clauses=[],
        transparency_scores={},
        draft_output={},
        guardrail_notes=[],
        confidence_score=None,
        confidence_inputs={},
        approved=False,
        escalation=False,
        escalation_reason=None,
        delivery_hold=True,
        advisor_notification={},
        output={},
        target_language=target_language,
    )
