"""Guardrails package — shared checks imported by nodes.

Per AGENTS.md rule 3: guardrails are distributed, not one stage.
The five separate controls are:
  1. Input validation      → input_validate node
  2. Rate limiting         → rate_limiter decorator on llm_call()
  3. Ingestion screening   → rag/ingestion_screening.py
  4. Stage 4 compliance    → guardrail node
  5. Human escalation      → escalate node

This package provides reusable check functions that multiple nodes
import — it is NOT a single guardrail stage.
"""
