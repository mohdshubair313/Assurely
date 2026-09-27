"""Retriever — citation-linked retrieval from the vector store.

Used by domain agents (health_domain_agent, life_domain_agent) to
find relevant policy clause wording for a given user query or profile.

Returns structured results with citation metadata:
  {claim, source, url, retrieved_at, last_verified}

RAG is used ONLY for clause wording and explanations — never for
numbers, eligibility, or dates (AGENTS.md rule 5). Those come from
the rules_engine via policy_terms table lookups.

Every retrieved fact carries a source and last-verified date
(AGENTS.md rule 6).
"""

from __future__ import annotations

import logging
from typing import Any

from app.rag.vector_store import get_vector_store

logger = logging.getLogger(__name__)


def retrieve_health_facts(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    """Retrieve verified policy clause facts relevant to the health insurance query.

    All facts are guaranteed to carry source, url, retrieved_at, and last_verified
    per AGENTS.md rule 6.
    """
    vector_store = get_vector_store()
    facts = vector_store.similarity_search(query=query, top_k=top_k)

    # Sanitize / ensure compliance with AGENTS.md rule 6
    sanitized: list[dict[str, Any]] = []
    for fact in facts:
        claim_text = str(fact.get("claim", "")).strip()
        # Unknown provenance must stay missing so the guardrail can reject it.
        source_value = fact.get("source")
        verified_value = fact.get("last_verified")
        source_text = source_value.strip() if isinstance(source_value, str) else ""
        last_verified = verified_value.strip() if isinstance(verified_value, str) else ""
        url = str(fact.get("url", "")).strip()
        retrieved_at = str(fact.get("retrieved_at", "")).strip()

        sanitized.append(
            {
                "claim": claim_text,
                "source": source_text,
                "url": url,
                "last_verified": last_verified,
                "retrieved_at": retrieved_at,
            }
        )

    logger.info("Retrieved %d policy clause facts for query: %s", len(sanitized), query[:50])
    return sanitized
