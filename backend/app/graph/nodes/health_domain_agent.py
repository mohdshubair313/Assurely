"""health_domain_agent — Health Insurance Domain Agent.

Trigger: intent == "health" (or "both" in future phases).
Reads:   user_profile, messages.
Writes:  retrieved_facts (partial — health insurance portion).
Calls:   RAG retriever + LLM.

Covers individual health, family floater, and critical illness policies.
Runs in parallel with risk_analysis as part of Stage 2 fan-out.

Uses need-fit framing only — never ranking language (AGENTS.md rule 1).
Every retrieved fact must carry source + last-verified date (rule 6).
"""

from __future__ import annotations

import logging
from typing import Any

from app.graph.state import SessionState
from app.rag.retriever import retrieve_health_facts

logger = logging.getLogger(__name__)


async def health_domain_agent_node(state: SessionState) -> dict[str, Any]:
    """Execute the health_domain_agent node in Stage 2 parallel fan-out.

    Queries the vector store for verified policy clauses relevant to the user's
    profile (family structure, pre-existing conditions, hospital cost tier)
    and populates state['retrieved_facts'].
    """
    user_profile = state.get("user_profile", {})
    session_id = state.get("session_id", "default_session")

    # Formulate targeted retrieval queries based on profile attributes
    queries: list[str] = ["hospitalization room rent single private room restoration recharge"]

    if user_profile.get("pre_existing_conditions"):
        queries.append("pre-existing disease waiting period 36 months specific illnesses")

    if user_profile.get("dependents", 0) > 0:
        queries.append("family floater cumulative bonus maternity pre and post hospitalization")

    # Retrieve verified facts from vector store / seed corpus
    retrieved_facts: list[dict[str, Any]] = list(state.get("retrieved_facts", []))
    seen_sources = {f.get("source") for f in retrieved_facts}

    for q in queries:
        facts = retrieve_health_facts(query=q, top_k=2)
        for f in facts:
            if f.get("source") not in seen_sources:
                seen_sources.add(f.get("source"))
                retrieved_facts.append(f)

    logger.info(
        "Health domain agent completed for session %s: %d facts retrieved",
        session_id,
        len(retrieved_facts),
    )

    return {"retrieved_facts": retrieved_facts}
