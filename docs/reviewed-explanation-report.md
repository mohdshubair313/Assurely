# Reviewed explanation report

Checkpoint: 2026-11-02. One existing node changed: `explanation_report`.
The helper `app/graph/reviewed_report.py` is deterministic and does not route the
graph, query a model, approve a policy or authorize delivery.

## Rendering contract

The adapter consumes only `reviewed_graph_comparison` results from imported
`policy_terms`. It binds each result to the current explicit comparison request
and scenario. Available facts require matching publication digest, term row,
review event and human-review date, complete fact/scope citations, a nonexpired
snapshot and applicable date/cover/options/conditions. Unknown or false conditions
cannot become an affirmative explanation. Unavailable capabilities carry only
operational status/reason metadata and no policy claims.

Each deterministic statement includes insurer/product/UIN/variant, the exact field
value and its applicability/condition scope. Integer formatting preserves paise;
discrete options are not interpolated into a range. Calendar months remain calendar
months. Age bounds preserve their reviewed completed-years or nearest-birthday
basis, including explicit unbounded upper age. Boolean scope retains grouped AND/OR
semantics. These fields do not establish personal eligibility or a payable claim.

Every statement carries the actual review date and source references: term row,
publication digest, verification event, PDF page, clause, quote, URL and hash.
Applicability and condition references remain separate from original fact sources;
reviewed note mappings retain their evidence. Existing compliance validation and
exact-evidence claim-support checks run on these templates. Oversized statements
fail the existing support limit instead of silently dropping scope.

## Hold and limitations

Report generation runs even when guardrail has escalated the turn. A populated
report has `report_status=reviewed_report_held`, `customer_delivery_authorized=false`
and `requires_fresh_lookup=true`. The existing API refuses that status even if
approval/hold flags incorrectly suggest release. No graph edge, guardrail,
escalation node or delivery route changed in this checkpoint.

Validation here checks a lookup snapshot; it cannot detect a publication revoked
after that lookup or independently authenticate modified in-memory evidence.
Release still requires a fresh database lookup and comparison against the report's
exact values/scope/review provenance, followed by applicable advisor authorization.
Do not enable release by changing the status string alone.

Templates currently report English explicitly, matching the existing deterministic
status-report convention. They do not translate policy values or wording through
a model. No real insurer policy, tariff or calculator assumption was approved;
application migration 006 is still pending.

## Acceptance evidence

88 tests pass: reviewed-template cases, existing report/claim-support regressions,
and two actual disposable-Postgres import-to-report checks using synthetic policy
PDFs. Tests cover paise precision, both wait units, unbounded age, separate citation
roles, partial results, grouped conditions, missing sources, mismatched identities,
expiry, scenario mismatch, rejected input and API redaction despite stale release
flags. Evidence: `artifacts/reviewed-report-tests-20261102.xml`. Targeted Ruff and
mypy pass. This is software validation, not semantic model calibration or real
policy-source verification.

Next: fresh delivery-time publication/condition/term revalidation and controlled
advisor release, preserving generation/delivery separation.

Follow-up: [delivery-boundary revalidation](reviewed-delivery-gate.md) is now wired
on both public read paths. Durable report-bound advisor authorization/release is
still pending; reviewed reports remain held.
