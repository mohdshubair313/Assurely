"""explanation_report — Stage 5: generates the final user-facing output.

Trigger: after guardrail (runs REGARDLESS of escalation status).
Reads:   draft_output, guardrail_notes, retrieved_facts, target_language.
Writes:  output.
Calls:   LLM rendering call in target_language.

CRITICAL CONTRACT (AGENTS.md rule 4):
  - This is the ONLY node that writes ``output``.
  - It runs even when escalation == True — so the human advisor has
    something concrete to review, not a blocked draft.
  - Escalation gates DELIVERY (in the escalate node), not GENERATION.

Every claim in output carries a source and a last-verified date
(AGENTS.md rule 6 — no exceptions).

Output is rendered in the user's detected language (target_language).
"""
