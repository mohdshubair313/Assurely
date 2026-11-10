# Human review request and operator intake implementation

Date: 2026-11-08. Scope: the request/status branch of voice FR17/FR18 and
AC13/AC14, implemented as a separate authenticated case workflow. This is a local
implementation checkpoint, not customer launch or actual human contact evidence.

## Implemented contracts

| Route | Authority and effect |
| --- | --- |
| `POST /v1/sessions/{session_id}/human-review` | Verified Clerk case owner; body contains only UUID `request_key`; commits a durable receipt and creates/reuses an open escalation |
| `GET /v1/sessions/{session_id}/human-review` | Same owner; returns the latest receipt or `request: null`; remains readable when creation is disabled |
| `GET /v1/admin/human-review-queue?limit=25` | Verified Clerk server-controlled admin, excluding designated test accounts; bounded private intake projection |
| Existing admin assignment | Separate audited assignment to a configured human advisor; queue reads cannot assign or approve |
| Existing advisor decision and report release | Existing independent qualification/assignment/report/evidence/expiry checks plus the new request chronology check |

Creation requires `HUMAN_REVIEW_REQUESTS_ENABLED=true`, Clerk and a durable staging
or production environment. The default is false. Development graph memory cannot
substitute for durable release authority. Audio consent, payment, subscriptions,
voice quota and provider configuration are not request prerequisites. A request
does not grant insurance-processing or other consent.

The response contains only request/case identifiers, database request time and a
queue status: `pending`, `assigned`, `in_review` or `decision_recorded`. Every
receipt response explicitly carries `delivery_hold: true`, `human_connected:
false` and `notification_dispatched: false`. `decision_recorded` describes a
later eligible human decision against the current report; it never authorizes
delivery. No report, medical details, private reason or advisor identity is
returned to the requesting customer.

## Persistence, locking and release protection

Additive candidate migration `015_human_review_requests` adds immutable request
receipts and ownership/integrity triggers. Existing migration files 011–014 are
unchanged. Populated downgrade refuses to discard receipt history. Empty-table
downgrade remains available. Application data and running services were not
migrated or restarted for this checkpoint.

Creation locks, in order: issuer/owner/request key; issuer/owner budget; existing
case/report head; selected escalation row. It normalizes issuer, owner and case
into a versioned SHA-256 request digest. The same key/digest retries the original
receipt; a conflicting case returns 409. Keys are scoped by verified issuer and
owner. Limits are three new requests per case in ten minutes and twenty per
owner in one hour. Retries are checked before consuming this budget. Existing
open assignments and their private reasons are preserved.
Selection deterministically prefers an existing `in_review` entry, then
`assigned`, then `pending`, with creation time and UUID breaking ties.

`requested_at` uses PostgreSQL `clock_timestamp()` after lock acquisition. Report
release holds the same case lock and requires the actual advisor decision time
to be strictly later than the latest request. Old approvals and historical
release-receipt retries therefore fail after a new request, even with the creation
flag switched off. Current source/evidence, independent actor, active assignment,
guardrail approval, exact turn/report, approval expiry and release-receipt checks
remain in force. No request mutates graph output or manufactures a human decision.

Schemas 013 and 014 remain compatible only while their later features are
disabled. Missing request storage with this feature enabled fails closed. When
request storage exists, persisted holds are enforced regardless of the flag.

## Frontend and operator intake

The existing handoff/comparison views now let an authenticated owner save or
refresh a case review request. The private voice development page links to this
separate case workflow. Both case and account scope the view and retry key.
Only an opaque operation key is kept in session storage; uncertain writes retain
it across reload. Successful confirmation permits a later intentional fresh
request. Storage failure prevents dispatch rather than creating an unrecoverable
operation. A new request or status refresh clears any displayed report and old
review status; opening a report again performs the existing fresh release checks.

The same-origin BFF allowlist accepts only the closed command, rejects duplicate
JSON members before parsing can collapse them, uses server SDK credentials and
rejects cross-origin writes. Client response decoding checks case binding and
refuses connected/notified/released or injected-authority states.

Operator intake shows one latest customer request per active escalation, scoped
to the verified issuer and current owner. It returns only escalation/case/request
IDs, time and queue status. Default 25, maximum 100; `truncated` and
`pagination: first_page_only` make the limitation explicit. This is an API, not an
operator dashboard or a notification dispatcher. High-volume cursor navigation,
notification delivery and staff operational acceptance remain separate work.

## Verification and requirement boundaries

Changed files by responsibility:

- Persistence/service: `backend/alembic/versions/015_human_review_requests.py`,
  `backend/app/models/db/human_review.py`, model registration,
  `backend/app/db/human_review.py`, `human_review_queue.py`, `schema.py` and the
  existing `report_release.py` guard.
- API/configuration: `backend/app/api/v1/human_review.py`,
  `human_review_queue.py`, router registration, core settings and the backend/deploy
  environment examples. No private environment file changed.
- Frontend: `HumanReviewPanel.tsx`, `CaseReportView.tsx`, `VoiceDevelopment.tsx`,
  `lib/human-review-attempt.ts`, contracts/client, the existing BFF, contract/Clerk
  boundary tests and the contract-test compile command in `package.json`.
- Tests: `test_human_review.py` in unit/integration, unit queue checks and the
  existing advisor migration fixture. Specs, this report, the phase checkpoint,
  root voice report and progress record the implementation boundaries.

- **TESTED:** 1,020 full offline backend unit tests passed, including 11 request
  and 23 queue unit cases. These focused cases overlap the full count.
- **TESTED:** 15 new real PostgreSQL integration tests passed, with independent
  transactions, concurrent same-key starts, distinct-key budgets, ownership,
  immutable history, strict timestamp comparison, flag rollback, subprocess
  recovery, old approval/receipt rejection, fresh authorized human decision,
  queue scope/projection, populated downgrade refusal, committed HTTP receipt and
  active-assignment preference across older pending duplicates.
- **TESTED:** 11 existing advisor/release PostgreSQL regression tests passed.
- **TESTED:** 27 frontend contract/SDK-boundary tests, 14 media mocks and three
  development API checks passed. Production Next build, TypeScript, changed-file
  ESLint and targeted Python Ruff/mypy passed. None is genuine voice acceptance.
- **IMPLEMENTED / TESTED branch:** FR17 and AC13's idempotent saved-request
  alternative. Actual provider tool invocation and human operations are pending.
- **IMPLEMENTED / TESTED branch:** FR18 and AC14's subscription-independent
  human request path, including empty voice quota/consent tables.
- **NOT IMPLEMENTED here:** live transfer, notification dispatch, operator UI,
  reviewed case-to-voice release, conversation captions or conversation summaries.
- **BLOCKED / UNVERIFIED:** genuine Vaani audio/BYOL/termination/language and
  qualified human launch acceptance; no new external provider request was made.

Receipts: `artifacts/human-review-full-unit-20261108.xml`,
`artifacts/human-review-postgres-20261108.xml`,
`artifacts/human-review-queue-unit-20261108.xml`,
`artifacts/human-review-release-regression-20261108.xml`.
Final parsed result manifest: `artifacts/human-review-results-20261108.json`.

Review corrected three frontend gaps before completion: duplicate JSON keys lost
by gateway parsing, previous review status surviving an uncertain write and a
previously displayed report surviving a review-status refresh. Synthetic fixture
configuration was corrected to HTTPS staging origins and seeded advisor FK rows;
those initial failures are not application pass evidence.

An existing advisor migration regression initially failed because its fixture
downgraded 007 while newer trigger dependencies from 010 remained installed. The
test now reverses every descendant in order, exercises the empty 007 round trip
and restores descendants. Its populated-data refusal assertion is unchanged;
no migration or database constraint was weakened.

## Rollout and next work

Do not activate customer calls, production billing or new request creation from
this report. A backed-up migration through 015, durable Clerk staging and actual
authorized operator assignment/review/release acceptance are required first.
Existing application schema remains 013; this source checkpoint is not deployed.

Next implement explicit reviewed case-to-voice binding and source-linked captions
using fresh existing release authority, without a second report writer or knowledge
base. Keep provider invocation and genuine fictional audio acceptance gated until
configuration work resumes. Full merchant cancellation/refund terms and vendor,
privacy, accessibility and human operational acceptance remain open.
