# Reviewed policy terms and graph comparison

Checkpoint: 2026-11-02. Schema and graph-state changes were flagged before the
implementation. Routing and the report/escalation nodes are unchanged.

## Database representation

Migration `006_reviewed_policy_terms` adds `record_kind`, `publication_digest` and
`reviewed_facts_json` to the existing `policy_terms` table. A `reviewed_v1` row has
an exact publication digest and stores only the typed, normalized facts in that
manifest's capabilities. Discrete cover amounts remain integer paise, age retains
its reviewed basis and unbounded/finite distinction, and waits retain days or
calendar months. Unsupported capabilities remain unavailable.

Reviewed rows deliberately have null legacy document/date/amount/age/day columns;
their transaction-date window is a separately reviewed applicability rule, not a
generic `effective_date`. A database check constraint keeps legacy and reviewed
representations disjoint. The existing legacy comparison's document inner join
cannot select reviewed records. Legacy records keep their document and effective
date requirements and values after the migration. Immutable triggers reject
update/delete of reviewed rows and conversion of a legacy row into a reviewed row.

A publication may be represented once in `policy_terms`. The operator publisher
can call `POST /v1/policy-publications/{digest}/term-import` with a request UUID
and the **current** `publication_event_id`. The endpoint checks publisher
authorization, locks the identity/draft, revalidates source bytes and review
evidence, checks the live event again, and writes the exact snapshot and actor-bound
idempotency receipt in one transaction. A retry with the same key is historical
only; it does not authorize a future lookup or customer delivery. A changed request
with the same key is rejected. Importing an already matching snapshot is safe;
incompatible stored content is rejected. Import does not approve a policy, change
the publication decision or populate unsupported terms.

Each graph lookup rechecks the live publication, representation review, source
bytes, explicit applicability, conditional rules and expiry. It then reads the
value from `policy_terms`, reconstructs the expected complete snapshot from the
immutable draft/manifest and refuses missing or mismatching rows. Facts include
the actual `policy_terms_id`, evidence, human-verification date and scope. Revoked,
expired, unimported, mismatched or incomplete capabilities return no facts.
No legacy or nearest-value fallback occurs. Validity is checked again at the end of
the combined comparison, but a later customer release still needs a fresh gate.

The migration downgrades only while there are no reviewed rows. Refusing to drop
the reviewed columns after import preserves audit evidence; a production rollback
with real reviewed rows needs a separate data-preserving migration plan. Database
administrators with privileges to disable triggers or bypass application services
remain outside this control.

## Explicit input and graph behavior

`POST /v1/message` accepts an optional `reviewed_comparison_request` using the same
explicit per-publication structure shown in
[reviewed comparison preview](reviewed-comparison-preview.md). It is limited to
64 KiB after serialization, strictly validated, and rejects duplicate JSON keys.
Policy issue/renewal date, cover basis, selected options and requested capability
are supplied by the caller; optional conditional inputs stay unknown. A digest or
scenario supplied by the caller does not grant publication or delivery approval.

The request is scoped to the current turn and replaced with null on the next turn
unless explicitly supplied again. It is retained in the current in-memory graph
checkpoint for that turn; it is not a consented profile-memory update. The graph
uses the operator-configured `AUTH_ISSUER` as the publication namespace, never an
issuer supplied in the scenario.

Outside development, `compare_verify` uses the new `policy_terms` path only when a
valid explicit scenario and configured issuer are present. The intermediate
`reviewed_comparison` preserves available and unavailable capabilities, without
inventing a premium, eligibility verdict, score or full-policy conclusion. Database
errors fail closed. The existing legacy comparison and its unverified seed values
remain blocked in non-development environments.

**Customer delivery remains held.** The existing `publication_gate` remains
`blocked`, Stage 4 disapproves/escalates, and API responses redact the intermediate
comparison. The report node now renders these scoped facts through the
[reviewed report adapter](reviewed-explanation-report.md), and the
decision-trace writer now records the comparison's term/source identifiers as
[historical lookup evidence](reviewed-comparison-trace.md). A future release needs a
fresh authorization check at delivery; a historical graph checkpoint is not enough.
The graph adapter in this checkpoint modifies `compare_verify` only, without adding
a node or changing edges.

## Verification and operational boundary

Focused tests use synthetic policy evidence and identities in a disposable,
explicitly named Postgres database. They exercise independent signed HTTP import,
graph lookup, hold/redaction, date/option input, turn-to-turn reset, transaction
rollback/idempotency, changed content, revocation and expiry, tampered stored data,
foreign issuer, immutability, and migration over an existing legacy row. The full
migration chain was exercised up/down/up with no reviewed rows; an attempted
downgrade with a reviewed row is separately checked to fail. See `PROGRESS.md` for
test count and evidence path.

Migration 006 was not applied to the application database. Application processes
using the new ORM need migration 006 before they query `policy_terms`; coordinate
that upgrade with deployment and a data-preserving rollback plan. No real insurer
policy, tariff or calculator assumption was approved during this checkpoint.
