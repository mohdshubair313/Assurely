# AGENTS.md

Multi-agent insurance advisory platform (India). This file is the map, not the manual — full detail lives in `docs/`. Read `PROGRESS.md` before starting any task. Update it before ending any session.

## Hard rules — never violate these, regardless of the task

1. **Never use "rank," "ranking," "best," or "top" in any user-facing text.** Every comparison is need-fit framing only. This is a compliance requirement, not a style preference.
2. **Routing between nodes is deterministic code, never an LLM decision.** Conditional edges over explicit state fields (`intent`, `escalation`, `approved`, `missing_fields`). No node asks an LLM "what should happen next."
3. **Guardrails are distributed, not one stage.** Input validation, rate limiting, ingestion screening, the Stage 4 compliance check, and human escalation are five separate controls. Don't collapse safety logic into one place because it's convenient.
4. **`guardrail` approves; it does not write `output`.** Only `explanation_report` writes `output`, and it runs regardless of escalation status — escalation gates *delivery*, not *generation*.
5. **Anything with one correct answer is deterministic, not RAG.** Eligibility, exclusions, sum-insured limits, premium figures, effective dates → `policy_terms` table lookups. RAG is for clause wording and explanations only. No LLM-invented numbers, ever.
6. **Every claim in `output` carries a source and a last-verified date.** No exceptions, no matter how obvious the claim seems.

## Where things live

- `docs/insurance-platform-master-roadmap.md` — build order, phases, full tool list
- `docs/insurance-platform-tech-stack-hld-lld.md` — state schema, node table, Postgres schema, API surface, guardrails inventory, data architecture
- `docs/insurance-platform-eval-harness.md` — decision provenance, eval categories, metrics, feedback validation

## Current scope (Phase 1 — see master roadmap for the rest)

One channel (web chat), one product type (health insurance). Life insurance, WhatsApp, voice, multilingual output, family sharing, and renewal reminders are real future scope — do not build them now unless explicitly asked.

## Before you touch the schema or routing logic

Stop and flag it instead of proceeding silently. These are the two places where inconsistency across different tools/sessions compounds the most.

## Session pacing

Implement one graph node per session, then pause for user review. Do not bundle
`explanation_report` and `escalate` implementation into one session. Stage 5 is
paused pending review of the September 25 preflight and frontend changes in
`PROGRESS.md`. Maintenance fixes are documented separately from new-node work.
