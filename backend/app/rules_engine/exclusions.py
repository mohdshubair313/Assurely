"""Exclusions lookups — deterministic policy_terms queries.

Reads the ``exclusions_json`` column from ``policy_terms`` and
returns the list of exclusions applicable to a given user profile:
  - Pre-existing conditions and their waiting periods
  - Permanent exclusions
  - Conditional exclusions based on age or health flags

This is NEVER an LLM call (AGENTS.md rule 5). Exclusion lists
come from structured data, not from RAG or generation.

The compare_verify node uses this to populate hidden_clauses
and ensure exclusions are surfaced prominently, not buried.
"""
