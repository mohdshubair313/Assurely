# Durable advisor report review

Checkpoint: 2026-11-02. Migration 007 and API changes were flagged before editing.
No graph node, routing edge or generated output changed.

Follow-up (2026-11-03): [durable current reports and release receipts](report-release.md)
now implement the release service boundary. The production guardrail remains held;
the remaining-work statements below describe this earlier checkpoint.

`advisor_reports` stores immutable snapshots whose digest binds identity issuer,
database session, authenticated owner, exact report, scenario and reviewed evidence.
Chat history, free-form profile and model diagnostics are excluded. Scenario
predicates remain because they define review scope. This is audit storage, not
consented profile memory. `advisor_decisions` stores append-only approve/revoke
events, actor/issuer, revision, idempotency key/fingerprint, reason and expiry.

Database triggers reject update/delete. Empty downgrade is supported; populated
downgrade is refused. Restrictive session foreign keys preserve audit evidence and
must be accounted for in retention/deletion operations instead of silently
cascading away review records.

`ADVISOR_SUBJECTS` is a separate empty-by-default allowlist. Existing verified
RS256 issuer/audience/JWKS authentication supplies identity. Token roles and body
identities cannot grant access. Authorized advisors can inspect issuer-scoped
reports but cannot review their own. Database/checkpoint ownership must match.

## API and transaction contract

- `POST /v1/advisor-reviews/sessions/{session_id}/snapshot` stages only the server
  checkpoint after fresh evidence checks; caller report content is not accepted.
- `GET /v1/advisor-reviews/{digest}` returns exact report/scenario, revision and
  pending/approved/expired/revoked review status.
- `POST /v1/advisor-reviews/{digest}/decisions` accepts `request_key`,
  `expected_revision`, `action`, `reason`, and `expires_at` for approval only.
  Bodies are bounded to 16 KiB; duplicate keys and extra fields are rejected.

Approval freshly validates policy evidence. Expiry must be future, within seven
days and no later than the earliest cited publication expiry. Request-key and
revision locks serialize retries and competing decisions. Changed retry content
fails. Exact retries return historical receipts, including after later revocation.
Revocation does not require healthy policy sources. Lock order is request key
(decisions only), report digest, then publication locks; staging uses the same
report-before-publication order. Writes and receipts are transactional.

## Release boundary and remaining work

All responses say `customer_delivery_authorized=false`. This completes advisor
approval/revocation, not customer release. An old approved snapshot remains audit
evidence after a new turn; its receipt does not establish current-report authority.
Current graph checkpoints remain in memory, and missing checkpoints fail closed.

Next: durable current-report/turn binding, current advisor authorization plus
independent guardrail approval, fresh policy verification and a release receipt
committed in the same locking transaction. Customer delivery stays held. This
checkpoint does not implement release receipts, lift the publication hold, apply
application migrations or configure real advisors.

## Validation

35 focused/regression tests plus one migration test pass with synthetic policies
in disposable Postgres. Coverage includes signed HTTP, unauthorized/self-review,
issuer isolation, concurrent retry, stale revision, changed retry content,
rollback, immutability, expiry and advisor revocation after publication revocation.
Empty migration downgrade/upgrade succeeds; populated downgrade is refused.
Targeted Ruff, four-file mypy and diff checks pass.

Evidence: `artifacts/advisor-review-tests-20261102.xml` and
`artifacts/advisor-migration-tests-20261102.xml`. No real insurer/advisor approval
is claimed. Application migrations 006/007 remain pending.
