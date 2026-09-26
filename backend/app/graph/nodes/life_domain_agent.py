"""life_domain_agent — Life Insurance Domain Agent.

DEFERRED: Life insurance is explicitly out of scope for Phase 1.
Per master roadmap § 1 and AGENTS.md "Current scope": health insurance
only in v1. Life insurance and this agent wait for Phase 5.

When implemented, this will:
  Trigger: intent == "life".
  Reads:   user_profile.
  Writes:  retrieved_facts (partial — life insurance portion).
  Calls:   RAG retriever + LLM for term, endowment, and ULIP analysis.

This file exists in the skeleton to match PROJECT_STRUCTURE.md and
LLD § 7.2's node table. It is not wired into the graph until Phase 5.
"""
