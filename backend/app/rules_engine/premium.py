"""Premium lookups — deterministic rate table queries.

Reads the ``premium_rate_table_json`` column from ``policy_terms``
and returns the applicable premium for a given:
  - Sum insured amount
  - Entry age
  - Policy variant (individual / family floater / etc.)
  - Any applicable riders

This is NEVER an LLM call (AGENTS.md rule 5). Premium figures
come from the structured rate table, not from RAG or generation.
"""
