"""Injection screening — detects prompt injection in user input.

Used by input_validate as the first line of defense (distributed
guardrail — AGENTS.md rule 3).

Screens for:
  - Direct prompt injection attempts (instructions to ignore system prompt)
  - Jailbreak patterns
  - Role-play manipulation attempts
  - Encoded/obfuscated instruction injection

Suspicious inputs are flagged and may trigger escalation
rather than being silently processed.
"""
