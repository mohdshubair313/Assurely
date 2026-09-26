"""input_validate — entry-point node for every incoming message.

Trigger: new message arrives.
Reads:   raw input from the user.
Writes:  validated input (sanitized, schema-checked).
Calls:   schema/PII checks (from app.guardrails.pii_scrub).

Responsibilities:
  - Validate message structure against expected schema.
  - Run PII scrubbing (distributed guardrail — AGENTS.md rule 3).
  - Run injection screening (distributed guardrail).
  - Detect target_language on the first turn ("hi", "en", "hi-en-mixed")
    and write it to state (LLD § 9, v3 alignment).
  - Pass validated input downstream.
  - Does NOT make any LLM calls — this is pure validation logic.
"""
