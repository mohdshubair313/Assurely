"""Langfuse integration — tracing every agent step.

Per eval harness § 9: Langfuse is the recommended starting point —
open-source, MIT-licensed, fully self-hostable. No data leaves
the infrastructure, which matters for DPDP posture.

Responsibilities:
  - Initialize the Langfuse client on app startup
  - Provide decorators/context managers for tracing graph node execution
  - Log per-node: input/output hashes, latency, token count, provider used
  - Feed the audit trail's technical backbone
  - Track latency (p50/p95 per node), cost (₹/session), guardrail catch rate

Galileo is the alternative if managed guardrails at scale become
needed later (eval harness § 9 — note Cisco acquisition caveat).
"""
