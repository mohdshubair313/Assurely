"""Ranking language check — enforces AGENTS.md rule 1.

Scans any user-facing text for prohibited ranking language:
  - "rank" / "ranking"
  - "best"
  - "top"
  - Other superlative or comparative terms that imply an ordering

This is a COMPLIANCE requirement, not a style preference.
Every comparison must use need-fit framing only.

Used by:
  - guardrail node (Stage 4 compliance check)
  - explanation_report (final output validation)

Returns: list of violations with line/position context for debugging.
"""
