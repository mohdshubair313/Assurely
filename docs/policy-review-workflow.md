# Durable policy-review staging - 2026-11-02

**Later checkpoint on 2026-11-02:** The separate [publication service gate](policy-publication-gate.md)
now implements typed applicability/conditions, authenticated capability publication,
overlap/freshness checks and fresh lookups. The staging APIs described below still
grant representation acceptance only; their blocked import diagnostics do not
become publication credentials. The remaining-work section below records the
earlier staging checkpoint; current next work is the reviewed comparison/report
adapter and qualified real-source/tariff/calculator review.

Implemented the next bounded priority-2 checkpoint: persist normalized proposals and original PDF bytes, record authenticated representation reviews, and audit blocked import checks. **No source was production-approved, and no policy was published into customer lookups.**

## What changed

Migration `004_policy_review_staging` adds five tables:

| Table | Purpose |
| --- | --- |
| `policy_source_blobs` | Deduplicated pinned PDF bytes keyed by SHA256; individually bounded to 20 MiB |
| `policy_review_drafts` | Exact normalized draft, digest, server timestamp and submitting issuer/subject |
| `policy_review_facts` | Ten individual field records, preserving both normalized and original source representations |
| `policy_review_events` | Append-only representation acceptance, rejection and revocation, bound to draft digest and revision |
| `policy_workflow_receipts` | Actor/issuer-scoped idempotency keys, request hashes and immutable response/audit receipts |

The migration adds no columns to `policy_terms` and does not change graph routing or current runtime selection. Its UPDATE/DELETE triggers reject mutation of all five tables; source corrections and changed decisions become new records. These controls do not protect against a privileged database administrator disabling triggers or truncating tables. Source bytes have no anonymous download endpoint.

Schema changes were flagged before implementation, as required by AGENTS.md. The proposed production entities in the October 30 contract remain distinct from these review-staging tables. Approved applicability/rule-set storage and publication are still pending.

## Authentication and API contract

All routes require the existing trusted-issuer RS256 token checks plus an explicit operator-managed `POLICY_REVIEWER_SUBJECTS` allowlist. The setting is a JSON array of subject UUID strings under the configured `AUTH_ISSUER`. It defaults to empty; no reviewer was configured in this session. The existing issuer/audience/HTTPS JWKS configuration is still required. A customer role, request-body reviewer name or client token role claim cannot grant access.

| Route under `/v1/policy-reviews` | Behavior |
| --- | --- |
| `POST /drafts` | Validate actual PDF bytes and normalized draft, then atomically stage sources, draft, ten facts and receipt |
| `GET /drafts/{digest}` | Read the draft and review history with current representation-review state |
| `POST /drafts/{digest}/reviews` | Record a revision-checked representation decision using verified identity and server time |
| `POST /drafts/{digest}/import-checks` | Revalidate persisted sources and record a blocked import diagnostic; never publish |

Staging JSON: `request_key` (UUID), `draft_json` (serialized `policy-rule-draft-v1` object, not the CLI envelope), and `sources_base64` (source-ID to exact PDF bytes encoded as base64). The complete request is bounded to 60 MiB, draft JSON to 512,000 characters, source count to 20 and each decoded PDF to 20 MiB. Keys must match the draft source set exactly. Duplicate JSON keys, invalid base64, changed PDFs and altered normalized values fail. Uploaded URLs are not fetched. Errors do not echo policy text.

Review JSON: `request_key`, `expected_revision`, `action`, `reason`, and `expires_at` only when accepting a representation. Allowed actions are `accept_representation`, `reject` and `revoke`; acceptance requires a timezone-aware future expiry no more than 90 days away. This 90-day limit is an application workflow bound, not an insurance/legal validity rule. `expected_revision` must match the latest stored event. Revocation requires a previous acceptance and creates another event. Review/import-check bodies are bounded to 16 KiB and reject duplicate keys.

Import-check JSON contains only `request_key`. Its HTTP success means the diagnostic was durably recorded, not that an import occurred: response `status` is `blocked`, and `approved_for_import` / `production_approved` remain false. A representation review cannot resolve missing premium, applicability, conditions or source conflicts by changing a boolean. Offline preview blockers still refer to the missing **approved production** persistence/review path; staging storage does not satisfy that path.

Idempotency keys are scoped to issuer plus actor, across commands. Same key and content returns the historical receipt; changed content or a different command with the same key returns 409. Replayed review receipts are historical records, not current permissions. Use GET for current review state, or a new request key for fresh import diagnostics after expiry/revocation. Every request still passes current authorization before a receipt is returned.

Postgres transaction-scoped advisory locks serialize requests sharing an idempotency key. Draft row locks plus revision checks serialize competing review decisions. Sources are inserted in deterministic hash order. A transaction failure leaves no source/draft/fact/receipt fragments. Services require the caller's explicit transaction; API dependencies commit or roll back the entire operation.

## Validation performed

- **85 focused tests passed:** 7 real-Postgres workflow tests, 21 authorization/API tests and 57 existing source/draft contract tests.
- **55 existing authentication/API regression tests passed** in isolated Linux Docker with networking disabled. This is not a refreshed full backend suite.
- Targeted Ruff and mypy passed for the new implementation. Local tests emitted one existing dependency deprecation warning from Starlette/AnyIO.
- The full Alembic chain upgraded from empty to `004`, downgraded to base, and upgraded again in a disposable Postgres 16 database.
- Staged actual archived Care/HDFC/Star draft/PDF pairs in that isolated database: **3 drafts, 30 fact records, 7 PDF blobs**. Original draft digests matched. Proposals remained 6/6/5; all three review states were pending and import checks blocked.
- Restarted the isolated Postgres container and re-read/revalidated all three drafts from persisted bytes. Counts, digests, pending status and blocked import outcomes survived the restart. This verifies review-store durability, not LangGraph checkpoint durability.
- Docker reassigned the random host port on restart; the initial readback connection was refused. After discovering the new mapping, the readback passed. The isolated helper now takes `POLICY_REVIEW_TEST_DATABASE_URL` explicitly and rejects a different database name.
- Concurrent duplicate staging created one draft/receipt; simultaneous decisions against the same revision allowed only one; rollback, expiry, revocation and database immutability checks passed.

Receipts: `artifacts/policy-review-final-20261102.xml`, `artifacts/policy-review-real-stage-20261102.json`, `artifacts/policy-review-real-restart-20261102.json`. The standalone reproduction script for the one-off isolated real-source exercise is `artifacts/check_policy_review_real_20261102.py`. The versioned tests are under `backend/tests/integration/test_policy_review_workflow.py` and `backend/tests/unit/test_policy_review_api.py`.

Migration was applied **only to disposable test storage**. The application database, existing seed terms, real reviewer configuration and customer-facing policy selection were not changed. Test staging used synthetic operator identity; it was not qualified human approval. Docker Desktop was started to run the isolated checks; the task's disposable test container is removed after verification.

## Remaining work, in order

1. **Finish priority 2:** model/reconcile reviewed applicability and conditional rules, add authenticated production approval/publication with version overlap/freshness checks, obtain missing Care tariff evidence, and complete qualified calculator-assumption review. The current API accepts representation reviews only; it deliberately cannot grant publication authority. Do not label this checkpoint as a complete production importer.
2. **Priority 3:** verify live identity-provider configuration and ownership, replace memory-only graph checkpoints with durable state, and finish authenticated advisor release/delivery handling.
3. **Priority 4:** connect frontend API calls and test intake through comparison, report hold and advisor release, including restart/failure cases.
4. **Blueprint additions:** implement the claim-cost engine and subsequent exploration features on the reviewed rule model. No simulator, claim ledger or new graph node was added in this checkpoint.

Next implementation checkpoint: conditional/applicability representation and the production publication gate, using the staged evidence and review history. Care's unavailable tariff must remain an explicit missing capability throughout.
