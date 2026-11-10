# Voice phase implementation checkpoint â€” 2026-11-08

The owner requested implementation before further credential/dashboard work. This checkpoint
adds working backend and frontend code with synthetic tests. **It does not close all V2â€“V5
acceptance criteria or certify a production voice/subscription product.** No account probes,
agent changes, real calls, checkout, credential rotation or customer/billing activation occurred.

Latest extension: customer human-review request/status and bounded protected operator
intake are now implemented as a separate case workflow. New requests invalidate earlier
approval/release authority without invoking a provider or requiring voice quota.
Migration 015 and creation remain gated. See [the request implementation report](VOICE_HUMAN_REVIEW_IMPLEMENTATION.md)
for current tests and limits; the earlier next-task list below is historical for that item.

## Implemented code

Superseding next-item checkpoint (2026-11-09): explicit reviewed case binding and
source-linked browser report excerpts are implemented behind a default-off staging
gate. Fresh release checks and short presentation leases preserve holds. Actual
provider speech and live captions remain pending. See
[current implementation report](VOICE_CASE_BINDING_IMPLEMENTATION.md).

| Phase | New implementation | Status and boundary |
|---|---|---|
| V2b lifecycle | Managed Vaani create/status/connect/explicit-end adapter; persisted operation intents/leases; encrypted provider and room credentials; server-owned room binding before connect; owner-scoped start/status/connect/authorization/end APIs; worker recovery, cap/consent/rollback termination requests | IMPLEMENTED; contracts MOCKED. Actual provider handshake/audio/end remains UNVERIFIED. Direct trigger-call adapter is preserved and not mixed with managed tokens. |
| V2b frontend | Private `/voice-development` page mounts the existing LiveKit controller; distinct disclosure/microphone/vendor selections; microphone permission check before provider creation; same-key start recovery, same-session connection, muted reconnect, authorization heartbeat and durable end request | IMPLEMENTED; SDK behavior MOCKED and build/typing checked. Real microphone/device/mobile/browser acceptance NOT TESTED. Customer entry points remain disabled. |
| V3 evidence | Owner/current-processing-consent checks; follow-up bridge through the existing `send_message` pipeline; current-report delivery recheck; exact sourced sentences for speech; unsupported/held output blocked; no new calculator or knowledge base | IMPLEMENTED as gated server tools, not wired to synthetic BYOL. Real case-bound voice conversations and reviewed-report voice release are NOT IMPLEMENTED. No insurance data sent externally. |
| V3/V5 recap | Separate summary consent; encrypted, expiring report-excerpt records; idempotent case/report version binding; current evidence/hold check at read; deletion and worker purge after consent withdrawal/expiry | IMPLEMENTED/TESTED with synthetic report packets. This is a validated report excerpt, NOT a conversation summary or transcript. |
| V4 test billing | Explicit test-key-only subscription adapter; durable pending checkout before POST; no retry after uncertain creation; bound subscription ownership; raw-body HMAC receiver; event-ID/digest deduplication; captured-event validation; frozen allowance snapshot; non-destructive funding-period history and cancellation/halt receipt handling | IMPLEMENTED/TESTED as test infrastructure. A separate default-off funded-test gate connects verified test periods to the existing session ledger, enforces per-period spend and preserves original allocations during rollover. No approved prices, taxes, paid checkout UI, refunds or full commercial cancellation workflow. |
| V5 operations | Release-status inventory reports customer/billing disabled; no generated approvals; additive schema compatibility check; worker resumes pending operations and purges optional excerpts | IMPLEMENTED controls only. Vendor privacy/retention/deletion, qualification, merchant terms, real measurements, accessibility and rollout approval remain BLOCKED/UNVERIFIED. |

### Managed lifecycle

```mermaid
sequenceDiagram
    participant UI as Private development page
    participant API as FastAPI
    participant DB as PostgreSQL
    participant V as Vaani managed API
    participant W as Recovery worker
    UI->>API: Verified owner + consent + same request key
    API->>DB: Reserve allowance; persist create intent
    API->>V: Create managed session once
    API->>DB: Encrypt session token
    API->>V: Read managed status / room
    API->>DB: Bind server-owned room
    UI->>API: Connect existing session
    API->>DB: Commit connect intent
    API->>V: Connect managed session once
    API->>UI: Short-lived authorization + scoped room credentials
    UI->>API: End request (or consent/cap triggers worker)
    API->>DB: Persist termination request
    W->>V: Disconnect with explicit_end=true
    W->>DB: Await trustworthy usage; retain reservation
    V->>API: Signed terminal webhook
    W->>DB: Existing event reconciler settles once
```

No database locks are held during provider HTTP requests. Mutations use entitlement â†’ session
â†’ provider binding â†’ managed operation. A crashed/timed-out create/connect becomes
`start_unknown`; it is never silently dispatched again. A confirmed managed end still lacks
authoritative duration until a trusted terminal event arrives, so reservations remain pending.
The official status URL embeds a session token; HTTP client logs redact that entire path.

The managed status contract is expected to provide the room before connect dispatches the
agent. This follows the inspected SDK and is covered by fixtures; the actual account must
prove that ordering before live acceptance. BYOL call-ID/path behavior must also be observed.
No generic dashboard-test bypass or self-created ownership binding was added.

## Schema and rollout

`014_voice_managed` adds managed operations, test subscriptions/periods/receipts and optional
recaps. Funding allocations reuse existing session/ledger records; database triggers reject
period overspend, cross-owner allocation and rematerialization. Migrations 011â€“013 are unchanged. Financial period facts are immutable; downgrade
refuses to discard populated new tables. Tested only in disposable PostgreSQL databases.
The application database remains at its existing 013 revision; no deployment/migration is
claimed here. 013 remains ready only with all new feature flags disabled; 014 is required
when enabling development audio, evidence tools or billing tests.

Before a later staging migration, take the documented encrypted backup, apply additive
Alembic head, refresh API/worker together, and verify readiness. Keep the current tunnel's
narrow allowlist intact. It deliberately does not expose development APIs or the new billing
callback. Do not change that allowlist merely to make dashboard tests succeed.

New private variable names, with no values:

```text
VOICE_DEVELOPMENT_ENABLED
VOICE_TOOLS_ENABLED
VOICE_BILLING_TEST_ENABLED
VOICE_FUNDED_TEST_ENABLED
VOICE_TOKEN_ENCRYPTION_KEY
VOICE_SUMMARY_RETENTION_HOURS
RAZORPAY_TEST_KEY_ID
RAZORPAY_TEST_KEY_SECRET
RAZORPAY_TEST_WEBHOOK_SECRET
VOICE_TEST_PLAN_ID
VOICE_TEST_PLAN_SECONDS
```

Existing Vaani/Clerk configuration remains unchanged. A persistent private Fernet key is
required for managed credentials/recaps; loss or rotation without a recovery plan prevents
decryption. No working key or sample production credential was generated or published.

## Requirements and acceptance

These are coverage additions, not declarations that entire criteria passed:

- FR01â€“FR04 / AC01â€“AC05: shared Clerk dependency, owner filtering, separate UI purposes,
  server consent checks and worker termination markers. Real account/device revocation remains pending.
- FR06â€“FR10 / AC06â€“AC08, AC21: mounted controls, permission checks before dispatch, persisted
  create/connect uncertainty, scoped credentials, same-session reconnect and duration/end controls.
  Actual audible disclosure, interruption, language and hard termination remain pending.
- FR11â€“FR16 / AC09â€“AC12: exact current report evidence and follow-ups reuse existing pipeline;
  holds/sources/verification dates are checked. No new expense simulator, arbitrary calculator
  figures, external voice tools or qualified-review release path is represented as complete.
- FR17â€“FR18 / AC13â€“AC14: existing independent human-review/text workflow is preserved;
  actual voice review-request/transfer integration is still NOT IMPLEMENTED.
- FR19â€“FR22 / AC15â€“AC18, AC23: signed test billing/immutable funding history and existing
  reservation settlement checks added. Funded test-period caps, known-unused release and rollover allocation are implemented and tested.
  Paid access, refunds, cancellation timing/terms and real billing remain NOT IMPLEMENTED or
  BLOCKED pending accepted contracts.
- FR23â€“FR25 / AC19â€“AC22: optional encrypted report excerpts and deletion/retention added;
  real conversation recap/captions, customer case entry and device/accessibility acceptance remain open.

## Files

- Backend: `app/voice/{managed_provider,managed,evidence,billing,funding,recaps,release}.py`;
  `app/models/db/voice_lifecycle.py`; `alembic/versions/014_voice_managed.py`;
  `app/api/v1/voice_development.py`; existing provider router, consent, worker, schema/readiness,
  configuration, gateway and offline test runner.
- Frontend: `components/product/VoiceDevelopment.tsx`, private development page,
  `lib/voice/api.ts`, existing BFF route validation, package script and lifecycle tests.
- Regression evidence is recorded below after final receipt collection. Prior uncommitted
  Clerk/V1/V2a code is preserved; no commit, push or production deploy.

## Remaining implementation order

1. Close managed-account call-ID/room-before-connect/no-fallback/termination acceptance using
   fictional data when the owner resumes provider configuration. Do not fabricate an accepted call.
2. Implement reviewed case-to-voice binding, source-linked captions and real human-review request
   status integration; keep current release checks on every channel. Implement only reviewed
   calculator scenarios; existing report numbers are not a new claim-expense simulator.
3. Agree commercial billing/cancellation/refund contracts, then build approved checkout
   disclosure/cancellation UI and confirm provider refunds and live subscription lifecycle.
   Test-period spending and rollover with outstanding reservations are implemented.
   An event receipt alone is not a complete subscription system.
4. Complete vendor deletion/retention, real device/language/accessibility measurements, operator
   alerts/rollback drills and responsible human launch approvals. Credentials alone do not close V5.

## Sources inspected

- [Vaani managed session SDK contract](https://docs.vaani.dev/sdk), including SDK 0.3.1
  resource/model source inspected from the published wheel on 2026-11-08; no SDK code executed.
- [Vaani BYOL protocol](https://docs.vaani.dev/guides/byol). Agent write-only settings remain
  separate from backend implementation; its untrusted system prompt is not adopted as authority.
- [Razorpay subscription creation](https://razorpay.com/docs/api/payments/subscriptions/create-subscription/)
  and [raw-body webhook verification/idempotency](https://razorpay.com/docs/webhooks/validate-test/).
- [Langfuse masking](https://langfuse.com/docs/observability/features/masking): preserve existing
  privacy-conscious wrapper/pin; no raw speech/recap arguments or new remote trace were exported.


## Final verification

- **986** full offline backend unit tests passed; **53** existing PostgreSQL regression tests passed.
- Final focused run: **38 passed** (**16 real PostgreSQL integration cases + 22 unit cases**),
  zero failures/errors/skips. The unit cases overlap the full suite; do not count them twice.
- Frontend: **14 media mocks + 3 development API + 23 existing contract tests passed**.
  Production Next build, TypeScript and changed-file ESLint passed. No actual microphone,
  audio, browser visual, mobile or language acceptance was exercised.
- Strict targeted mypy passed for **12 runtime files**, plus a final two-file recap/funding
  check. Changed Python Ruff and repository whitespace checks passed.
- Final candidate migration 014 CLI upgrade -> downgrade to 013 -> upgrade passed in an
  empty disposable database. Application database stayed at 013; no running service was
  restarted to activate the new routes. Local `/health` and `/ready` returned 200.
- Receipts: `artifacts/voice-next-unit-20261108.xml`,
  `artifacts/voice-next-regression-postgres-20261108.xml`,
  `artifacts/voice-next-final-targeted-20261108.xml`,
  `artifacts/voice-next-results-20261108.json`.

Initial failures and corrections: a cross-thread asyncio harness stalled and was replaced
with bounded tasks using independent real PostgreSQL transactions; this is not presented as
an application deadlock repair. The unauthenticated endpoint fixture needed a configured
synthetic IdP before expecting 401 instead of configuration-unavailable 503. A migration CLI
attempt raced disposable PostgreSQL startup; the readiness-checked rerun passed. The new
append-only billing receipt constraint exposed an actual autoflush ordering defect: an early
provisional INSERT was followed by an immutable status UPDATE. The service now adds the
final receipt once after processing, in the same transaction as funding. The final signed
billing, duplicate-event, ledger and period tests passed without weakening constraints.

Create UI and Langfuse guidance were applied. Existing privacy-conscious instrumentation
and its SDK pin were preserved; no remote trace or raw content was exported. Local Next.js
route-handler/client-boundary guides were checked against the implementation. No graph
node/edge, insurance report writer, production credential or existing applied migration changed.
