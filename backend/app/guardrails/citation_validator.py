"""Citation validator — ensures every claim carries a source (AGENTS.md rule 6).

Validates that every factual claim in ``output`` or ``draft_output``
has a matching entry in ``sources_per_claim`` with:
  - A source URL or document reference
  - A last-verified date

Claims without valid citations are flagged as violations.
Used by the guardrail node and as a post-check on explanation_report.

No exceptions, no matter how obvious the claim seems (rule 6).
"""
