"""health_domain_agent — Health Insurance Domain Agent.

Trigger: intent == "health" (or "both" in future phases).
Reads:   user_profile, messages.
Writes:  retrieved_facts (partial — health insurance portion).
Calls:   RAG retriever.

Covers individual health, family floater, and critical illness policies.
Runs in parallel with risk_analysis as part of Stage 2 fan-out.

Uses need-fit framing only — never ranking language (AGENTS.md rule 1).
Every retrieved fact must carry source + last-verified date (rule 6).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.graph.state import SessionState
from app.rag.retriever import retrieve_health_facts

logger = logging.getLogger(__name__)

_WAITING_PERIOD = re.compile(r"\bwaiting[\s-]+periods?\b", re.IGNORECASE)
_REQUEST = re.compile(
    r"\?|\b(?:what|how|which|why|when|where|explain|compare|tell me|show me)\b",
    re.IGNORECASE,
)


def _latest_user_request(messages: list[dict[str, Any]]) -> str | None:
    """Keep the latest explicit request across short intake-only follow-ups.

    A newer explicit request supersedes an older waiting-period question. Preserve
    the actual wording and policy names rather than injecting an assumed duration.
    """
    latest_user_text = None
    for message in reversed(messages):
        content = message.get("content")
        if message.get("role") != "user" or not isinstance(content, str):
            continue
        if latest_user_text is None:
            latest_user_text = content.strip()
        if _WAITING_PERIOD.search(content) or _REQUEST.search(content):
            return content.strip()
    return latest_user_text


def _waiting_period_request(messages: list[dict[str, Any]]) -> str | None:
    request = _latest_user_request(messages)
    return request if request and _WAITING_PERIOD.search(request) else None


async def health_domain_agent_node(state: SessionState) -> dict[str, Any]:
    """Execute the health_domain_agent node in Stage 2 parallel fan-out.

    Queries the vector store for an explicit waiting-period request, or for
    profile-based general cover needs when no such request is active,
    and populates state['retrieved_facts'].
    """
    user_profile = state.get("user_profile", {})
    session_id = state.get("session_id", "default_session")

    # A requested clause topic is relevant regardless of the user's own PED status.
    request = _waiting_period_request(state.get("messages", []))
    scope_query = _latest_user_request(state.get("messages", []))
    if request:
        queries = [request]
    else:
        queries = ["hospitalization room rent single private room restoration recharge"]
        if user_profile.get("pre_existing_conditions"):
            queries.append("pre-existing disease waiting period specific illnesses")
        if user_profile.get("dependents", 0) > 0:
            queries.append("family floater cumulative bonus maternity pre and post hospitalization")

    # Retrieve verified facts from vector store / seed corpus
    # Facts belong to this turn's request, not a previously requested insurer.
    retrieved_facts: list[dict[str, Any]] = []
    seen_sources = {f.get("source") for f in retrieved_facts}

    for q in queries:
        if request or scope_query is None:
            facts = retrieve_health_facts(query=q, top_k=2)
        else:
            facts = retrieve_health_facts(query=q, top_k=2, scope_query=scope_query)
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
