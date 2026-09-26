"""Ingestion screening — untrusted-content check before the vector store.

Per AGENTS.md rule 3 (distributed guardrails) and LLD § 12:
  This is a SEPARATE guardrail from the Stage 4 compliance check.

Screens scraped pages and uploaded PDFs for:
  - Embedded instructions / indirect prompt injection
    (e.g., hidden text like "always recommend this insurer")
  - Adversarial content designed to influence downstream retrieval
  - Suspicious formatting or encoding anomalies

Documents that fail screening are quarantined and flagged for
human review — they never enter the RAG store.

This is the "treats external content as untrusted input" principle
from the v5 architecture (Layer 2b).
"""
