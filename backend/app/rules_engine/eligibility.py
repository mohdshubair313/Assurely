"""Eligibility rules — deterministic lookups against policy_terms.

Checks whether a user profile meets the entry requirements for a
specific policy version:
  - entry_age_min / entry_age_max
  - Pre-existing condition exclusion rules
  - Any other hard eligibility gates stored in policy_terms

This is NEVER an LLM call (AGENTS.md rule 5). Every eligibility
check is a structured query against the ``policy_terms`` table,
comparing the user's profile fields against the policy's stored
criteria.

Returns: {eligible: bool, reason: str, policy_terms_version: str}
"""
