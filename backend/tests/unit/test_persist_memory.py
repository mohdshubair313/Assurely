"""Consent and evidence contracts for the per-turn persistence node."""

from typing import Any

from app.graph.nodes.persist_memory import _profile_memory_consent_granted, _sources_per_claim
from app.graph.state import SessionState, create_initial_state


def test_profile_memory_requires_user_identity_and_specific_active_consent() -> None:
    state = create_initial_state(session_id="memory-consent-test")
    assert state["consent"] == {"granted": False, "scopes": []}
    assert not _profile_memory_consent_granted(state)

    state["user_id"] = "00000000-0000-4000-8000-000000000123"
    state["consent"] = {"granted": True, "scopes": ["process_comparison"]}
    assert not _profile_memory_consent_granted(state)

    state["consent"] = {"granted": False, "scopes": ["save_profile"]}
    assert not _profile_memory_consent_granted(state)

    state["consent"] = {"granted": True, "scopes": ["save_profile"]}
    assert _profile_memory_consent_granted(state)


def test_sources_per_claim_preserves_retrieval_and_clause_provenance() -> None:
    state: SessionState = {
        "retrieved_facts": [
            {"claim": "Clause wording", "source": "Policy PDF", "last_verified": "2026-09-27"}
        ],
        "hidden_clauses": [
            {
                "policy_key": "Insurer|Product",
                "clauses": [
                    {"clause": "Room cap", "source": "Policy PDF", "last_verified": "2026-09-27"}
                ],
            }
        ],
    }

    sources: dict[str, list[dict[str, Any]]] = _sources_per_claim(state)
    assert sources["Clause wording"][0]["source"] == "Policy PDF"
    assert sources["Room cap"][0]["last_verified"] == "2026-09-27"
