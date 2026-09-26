"""Human Life Value (HLV) calculator.

Deterministic calculation — zero LLM involvement (AGENTS.md rule 5).
Computes an estimated human life value based on:
  - Current income
  - Expected working years remaining
  - Inflation-adjusted growth rate
  - Existing liabilities and assets
  - Number of dependents

This is called by the needs_intake and risk_analysis nodes
to size life insurance coverage requirements.

Deferred to Phase 5 (life insurance scope), but the calculator
module exists now for structural completeness.
"""
