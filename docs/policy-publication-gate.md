# Policy applicability and publication gate

**Later 2026-11-02:** [Reviewed policy terms](reviewed-policy-terms.md) documents
the additional authenticated term-import step and unit-preserving graph lookup.
Publication alone does not import a row or authorize customer delivery.

**Later checkpoint on 2026-11-02:** An authenticated internal
[reviewed comparison preview](reviewed-comparison-preview.md) now combines fresh,
explicitly scoped capability lookups. Existing lookup results additionally preserve
evidence for applicability and conditional interpretations. This does not connect
the customer report or release the non-development comparison hold.

Checkpoint: 2026-11-02. This implements a production-publication **service gate**, with
authenticated operator APIs and fresh deterministic lookups. It does not certify
the insurer sources or make the whole advisory application production-ready.

## Implemented boundary

Migration `005_policy_publication` adds immutable `policy_publications` and
`policy_publication_events`. The source draft, its PDF bytes, representation review
and workflow receipts remain in the existing `004` tables. No legacy `policy_terms`
row is rewritten. Schema changes were flagged before implementation.

A proposal freezes a versioned manifest and exact source-draft digest. A different
authorized publisher reviews the proposed interpretation, evidence, source review
record and declared capability scope. The server records identity, timestamp,
revision and expiry. A publication decision is bound to the exact current
representation-review event; renewed, expired, rejected or revoked representation
review invalidates the old publication until a new publication decision is made.

Capabilities currently supported:

| Capability | Required source facts | Meaning and limit |
| --- | --- | --- |
| `coverage_options` | `sum_insured_options` | Discrete integer paise options, INR; no interpolation or premium quote |
| `adult_entry_ages` | Minimum and maximum adult entry ages | Explicit finite/unbounded bounds and reviewed age basis; not a full eligibility verdict |
| `base_ped_wait` | PED wait | Original day/calendar-month unit; no personal coverage date, continuity arithmetic or claim settlement |

Premium, exclusions, co-pay, deductible, room-limit and claim-settlement capabilities
are not accepted by this contract. Their absence does not become zero, no exclusion,
or a blanket approval. Missing Care tariff data remains unavailable. Publishing one
supported capability cannot authorize any of these additional operations.

## Applicability and conditions

The manifest explicitly distinguishes issue-date applicability from renewal-date
applicability. It also declares individual/family-floater cover and an exact set of
selected optional benefits. Both calendar-date endpoints are inclusive. An unknown
end date blocks publication; a reviewed `no_declared_end` is distinct from unknown
and remains bounded by publication/review expiry. A product revision date is never
automatically treated as a customer's policy issue date. Customer policy-period
coverage is not inferred from this window.

Conditions use a bounded OR-of-AND grammar: at most 20 alternatives, each at most
20 predicates. An explicit `[[]]` means unconditional. Supported inputs are
`entry_age_years`, `residency`, `zone`, `portability`, and `continuity`; operators
and operand types are allowlisted. Only integer ages support inequalities. Unknown
input evaluates to unknown, not true; false and unknown release no facts. There is
no expression evaluator, SQL expression, code execution or model-driven routing.

Every condition and unresolved note attached to identity/applicability or a selected
capability needs an exact note mapping. Note identities bind field, note kind, array
position and original text. Mappings record disposition, rationale and pinned-page
evidence. A conditional mapping cannot be paired with an unconditional scope.
Notes outside the capability remain in the original immutable source draft.
Unsupported interpretations must wait for a new version of the contract.

Evidence validation checks quote/page/hash against the pinned PDFs. It establishes
byte and citation integrity, **not semantic truth, source authenticity or reviewer
qualification**. Those are explicit human/operator responsibilities: the manifest
records a source-authenticity/screening review reference or explanation, and the
publisher reviews it along with all interpretations. This service does not ingest
the documents into RAG or replace its separate ingestion screening.

## Operator API and authority

All endpoints are under `/v1/policy-publications`. Existing RS256 issuer/audience/JWKS
verification supplies the subject. Request-body identities, approval booleans and
token role claims cannot grant permission.

| Method and path | Authorization | Action |
| --- | --- | --- |
| `GET /requirements/{draft_digest}` | Reviewer | Read capability requirements and exact note IDs for a staged draft |
| `POST /` (registered without trailing slash) | Reviewer | Stage `{request_key, manifest}` after actual PDF validation |
| `GET /{publication_digest}` | Reviewer | Read manifest, current publication state and decision audit history |
| `POST /{publication_digest}/decisions` | Publisher | Publish or revoke the exact manifest with optimistic revision check |
| `POST /{publication_digest}/lookup` | Reviewer | Recheck publication, source integrity, applicability and conditions |

`POLICY_REVIEWER_SUBJECTS` and the new `POLICY_PUBLISHER_SUBJECTS` are independent
operator-managed JSON arrays of UUID subjects under `AUTH_ISSUER`. Both default to
empty. A publisher who also needs operator read/lookup access belongs in both lists.
No real reviewer/publisher was configured by this checkpoint.

A decision body contains `request_key`, `expected_revision`,
`representation_event_id`, `action` (`publish` or `revoke`), `reason` and
`expires_at` (required for publish, absent for revoke). The publication expiry must
be future, at most 90 days away, and no later than the bound representation review.
The 90-day limit is an operational review limit, not an insurer policy term.
The draft author and publication-proposal author cannot publish their own work.

A lookup body contains `capability` and `context`, for example:

```json
{
  "capability": "coverage_options",
  "context": {
    "transaction": "issue",
    "transaction_date": "2026-11-02",
    "cover_basis": "individual",
    "selected_options": [],
    "residency": "resident"
  }
}
```

This context is a declared scenario, not an authenticated customer schedule.
Available results contain exact structured facts, source quotes/URLs/PDF hashes,
the human publication-review date and event ID, conditions, applicability and
expiry. Unavailable results have an empty facts array and an explicit reason.
No legacy seed fallback occurs. Authorization is checked again for each API call;
lookup rechecks live database state on every request. An old receipt/result is not
authority for a future delivery or decision.

Bodies are bounded (512 KB proposal, 16 KB decision/lookup), duplicate JSON keys
and extra fields are rejected, and validation errors do not echo uploaded content.
Services require an explicit transaction and a verified operator principal.

## Transactions and concurrency

Idempotency is scoped to issuer, subject and request UUID; changed content with a
reused key fails. Responses are historical receipts, explicitly requiring fresh
lookup. Publication and audit receipt commit atomically. Failed transactions leave
no partial decision. Revocation appends an event rather than mutating history.

An advisory transaction lock serializes each issuer/UIN/variant family, followed
by the source-draft row lock. Marketing-label changes cannot evade the family lock;
UIN/variant cosmetic whitespace/case/Unicode differences are normalized for locking.
Overlapping active windows for the same capability/date-basis/cover/options are
rejected. Predicate differences are conservatively not treated as proof of disjoint
scope. Distinct review events/revisions must be explicitly reconciled; no newest-row
or implied-precedence selection is performed.

Append-only triggers prevent ordinary UPDATE/DELETE of publication records and
events, reusing migration 004's trigger function. They do not defend against a
privileged database administrator disabling triggers or truncating tables.

## Application integration and rollout status

The legacy comparison/report projection cannot preserve discrete cover gaps,
calendar-month units and conditional scope. It therefore now fails closed outside
`environment=development`; Stage 4 disapproves that blocked draft and escalates.
No seed DB query, seed premium, legacy policy facts or score is emitted by that
comparison path in staging/production. This is maintenance of two existing nodes,
not a new graph node or routing change. Development fixtures remain available.

**The reviewed comparison/report adapter is still pending.** Publishing a capability
does not silently enable the legacy projection. Until that adapter exists, a
staging/production advisory request stays held even if an operator lookup can return
reviewed facts. The new APIs are internal operator endpoints, not yet frontend APIs.

Migration 005 is tested in disposable PostgreSQL only; it has not been applied to
the application database. No insurer candidate was published, no source conflicts
were cleared on behalf of a human, and calculator assumptions remain unapproved.

## Verification and next work

Focused tests cover strict conditional types, three-valued evaluation, date/options
boundaries, missing capabilities, note mapping and forged evidence; signed API
authority and input limits; actual PostgreSQL concurrent publication, overlap,
rollback, revocation, expiry, restart/reconnection readback, immutable records and
review invalidation. Detailed counts and artifact paths are recorded in PROGRESS.md.
No live insurer approval or complete product-readiness claim follows from these tests.

Next: build the reviewed comparison/report adapter without losing capability scope
or verification provenance, then complete qualified applicability/condition review
for real candidates and approved tariff/calculator work. Auth deployment, durable
graph state and advisor release remain priority 3; frontend integration/E2E remains
priority 4. The blueprint claim-cost simulator requires additional rule families.
