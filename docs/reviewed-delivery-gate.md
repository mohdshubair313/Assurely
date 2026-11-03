# Delivery-boundary evidence revalidation

Checkpoint: 2026-11-02. Maintenance of delivery boundaries; no graph node, graph
routing, database schema or generated output changed.

`build_delivery_response` is called on message responses and session reads, after
their existing identity/ownership checks. Reviewed reports are checked afresh on
each request using the configured publication issuer. No state flag, notification
receipt or previous successful lookup is accepted as release authority.

`check_reviewed_delivery` snapshots the in-flight state and checks the report's
exact deterministic statements, citations, reply, adapter version and scope. It
rejects incomplete reports, unavailable capabilities and mismatched scenarios.
The live comparison service then revalidates publication and representation state,
source bytes, imported term integrity, date applicability, options and conditions
under its existing publication/draft locks. The resulting evidence must match the
report, including event ID, expiry, source hashes, exact values and JSON types.
Only lookup timestamps may differ. A revoked or changed publication requires a
new report and review; it cannot silently substitute new facts into old prose.

Both consistency and failure outcomes currently remain held. A positive check has
the reason `advisor_authorization_required`; it is not an authorization token.
Connection/transaction errors also hold the response without exposing diagnostics.
The synchronous response builder holds all reviewed snapshots even if someone
changes their status to ready or flips approval flags. Outside development, old
legacy checkpoints also stay held. Session reads cannot expose held messages,
citations or calculator values.

## Remaining release contract

Durable authenticated advisor sign-off is not implemented. The next checkpoint
must flag its schema design before editing and bind approvals to exact session,
owner, report digest and publication/scenario provenance. Approval revocation,
superseded reports, identity roles and idempotent release receipts need explicit
rules. A notification queue acknowledgement cannot stand in for advisor review.

The eventual release decision and receipt must use the same transaction that holds
the publication locks and performs the fresh check; do not cache this check and
release in a later request. Transaction-time consistency is not a guarantee that a
publication will remain unchanged after commit or during network delivery. No
customer delivery was enabled by this checkpoint.

## Validation

110 focused/regression tests plus one strict integer/float substitution test pass.
They cover both real HTTP delivery boundaries, database failure redaction, repeated
checks, report/scenario tampering, changed source/review/value/condition evidence,
production legacy holds and existing session ownership controls. A disposable
Postgres test imports a synthetic policy, generates a report, verifies current
evidence, revokes the publication and confirms the same old report fails the fresh
check. Application storage, real insurer approvals and migration state are unchanged.

Evidence: `artifacts/reviewed-delivery-tests-20261102.xml` and
`artifacts/reviewed-delivery-type-test-20261102.xml`.

Targeted Ruff, three-file mypy and `git diff --check` pass. The disposable test
database container was removed after verification.
