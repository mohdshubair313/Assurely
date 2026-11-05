# Reviewed product-fact guardrail contract

Version: `reviewed_product_facts_v1` · 2026-11-03

## Meaning of approval

`approved=true` means the exact selected product facts passed the deterministic
scoped adapter, current publication lookup and text compliance checks. It covers
only the requested capabilities: discrete cover options, adult entry-age fields
and/or base PED waiting periods. It is not personal eligibility, a premium quote,
calculator approval, a payment promise or customer delivery authorization.

The existing `guardrail` node is the only node extended in this checkpoint. Its
return contains approval, escalation, notes and confidence metadata; it never
writes `output` or a delivery decision. Graph edges and database schema are unchanged.

## Acceptance conditions

All conditions must pass on every invocation:

1. Accepted health input, no missing fields and a strict selected comparison request.
2. Reviewed comparison has complete status, bounded evidence and no missing
   capabilities. It matches the requested publication, scenario and capability order.
3. Facts originate in reviewed `policy_terms`. Sources, verification events/dates,
   exact units, options, age basis, applicability and satisfied conditions validate
   through the same deterministic adapter used by `explanation_report`.
4. No mixed legacy claims, structured contradictions, hidden-clause payload or
   additional draft fields. The old `publication_gate=blocked` marker is required
   as the producer's legacy-path hold; this node independently validates the
   reviewed branch instead of treating the marker as approval authority.
5. A new `compare_terms` call in the configured issuer's database transaction
   rechecks imported snapshots, publication/review authority, source bytes,
   revocation, expiry and conditions under the publication service's locks.
   The complete comparison must match exactly, including JSON numeric types;
   only comparison and per-capability lookup timestamps may differ.
6. Every rendered scoped claim passes the existing prohibited language and advice
   checks. Maximum 32 claims and 4,096 characters per claim match report limits.

Missing issuer, malformed data, timeout (30 seconds), database error, partial or
changed evidence set approval false and escalation true. Old approval/confidence
flags are ignored. Failure notes contain no raw exception or customer/source text.
There is no fallback to legacy terms or a model decision. Non-development legacy
drafts fail closed; development retains the existing legacy guardrail contract.

## Confidence and advisor review

The legacy completeness formula does not measure this scoped format and is not
used as a calibrated confidence estimate. `confidence_score=0.0` is an explicit
conservative compatibility placeholder, with `confidence_available=false` in
`confidence_inputs`. It is not a measured probability. No new calibration claim
or artificial 1.00 score is introduced.

Every scoped report escalates, even after guardrail approval. That mandatory
independent advisor review includes NRI, PED, senior and high-value scenarios;
this scoped contract never grants automatic customer delivery. Existing advisor
notification configuration and its limitations still apply.

## Generation and release

`explanation_report` still generates despite escalation, and the result retains
`reviewed_report_held`. The synchronous message/session response remains redacted.
The separate transactional release endpoint requires a current durable turn and
report digest, recorded guardrail approval, a still-authorized independent advisor
decision and another fresh evidence check before committing its receipt.

Guardrail lookup locks end when its transaction ends. This approval snapshot is
therefore not a reusable freshness credential: expiry or revocation after approval
must still block report binding or release. See [report release](report-release.md)
and [delivery revalidation](reviewed-delivery-gate.md).

## Validation and remaining gates

Focused tests cover repeat fresh lookups, exact source/value/event/scope matching,
unavailable and conflicting evidence, malicious labels, stale flags, missing
issuer, failures, report generation and delivery holds. Disposable-Postgres tests
exercise the actual guardrail with synthetic reviewed publications and transactional
release; this proves software enforcement, not insurer-source correctness.

Qualified real-source/tariff/calculator approval, deployment of migrations and live
identity/advisor configuration remain required. Full durable graph recovery and
frontend end-to-end integration remain later work. MIT licensing applies to the
repository's own software; dependencies and third-party policy material retain
their own terms.
