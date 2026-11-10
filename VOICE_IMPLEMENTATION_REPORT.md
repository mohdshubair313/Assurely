# Assurely voice implementation report

**Latest bridge checkpoint, 2026-11-09:** implemented complete-answer BYOL buffering,
fresh report/human-release checks before send, durable unknown-send/no-replay
receipts and cancellation of unsent obsolete responses. Report export additionally
requires its own current account-level permission with explicit UI withdrawal.
Candidate migration 017 and the feature flag remain inactive. Actual Vaani speech,
audible interruption, provider termination and customer/billing release are not
certified. See [current implementation report](docs/VOICE_BYOL_EVIDENCE_IMPLEMENTATION.md).

**Latest checkpoint, 2026-11-09:** immutable reviewed case-to-voice binding and a
source-linked reviewed text companion are implemented locally. Every read repeats
current consent/source/human release checks; the companion is not a live transcript
and sends no report content to Vaani. Candidate migration 016 and activation remain
gated. See [implementation evidence and limits](docs/VOICE_CASE_BINDING_IMPLEMENTATION.md).

**Latest human-review checkpoint, 2026-11-08:** implemented immutable customer
request/status receipts, protected operator intake and fresh-human-decision enforcement
on report release. The frontend saves/retries requests without voice minutes or audio
consent and distinguishes queued requests from actual contact. Default creation remains
disabled; migration 015 is a tested candidate, not an applied application migration.
See [implementation report](docs/VOICE_HUMAN_REVIEW_IMPLEMENTATION.md) for current
evidence and incomplete live/provider/operator acceptance.

**2026-11-08 implementation update:** managed lifecycle APIs/worker, mounted private LiveKit
development UI, current-report/follow-up evidence tools, consented encrypted report excerpts,
signed test billing and gated test-period spending/rollover are implemented. Customer calls
and paid billing remain disabled. This does not close live-provider or all V3?V5 acceptance.
The earlier 401/invalid-agent and unmounted-control statements are historical; account reads
passed on November 7. See [the phase implementation checkpoint](docs/VAANI_PHASES_IMPLEMENTATION_20261108.md)
for exact completed work, tests, deviations and remaining software/approval gates.


**Connection-error follow-up, 2026-11-07 (supersedes earlier account blockers):**
The running container had stale credentials. Recreated only API and recovery services;
private comparisons confirmed intended configuration. Real Vaani list/detail GETs returned
200 and verified owned development agent `985b8f87-be0a-4aba-9e76-d18ae8ef4668`. Zero calls
were created. No credential replacement is currently indicated by the dashboard error.

Fresh local and public ingress checks each passed **12/12**, including signed synthetic
receipt/deduplication, invalid-signature rejection and WebSocket rejection. Runtime
`VAANI_BYOL_ENABLED=false`, `VAANI_DEV_AGENT_REVIEWED=false`, `VAANI_DISPATCH_ENABLED=false`,
`VOICE_PROVIDER=disabled`; actual database provider-call bindings: **0**. A valid token alone
cannot establish an authorized session. Unknown-call WebSocket rejection was reproduced as
HTTP 403. The owner's specific dashboard request was not captured; its precise upstream
failure remains unverified. Healthy transport does not establish an authorized BYOL 101.

Owner reports URL/token saved with No fallback; independent post-save dashboard inspection
was interrupted. Dashboard webhook/signing settings and genuine vendor callback remain
unverified. Next engineering prerequisite is controlled server-owned dispatch/session binding
and verified provider termination/reconciliation, before a deliberate synthetic call. Do not
weaken consent, authorization or call binding to pass a dashboard indicator. No real audio,
customer calls or paid billing enabled. Temporary tunnel remains development-only.

Collected prior interrupted diagnostic test receipt: **59 passed**, zero errors/failures/skips;
Ruff passed for `vaani.py`, `vaani_preflight.py`, `test_vaani_preflight.py`. These are mocked
regressions, separate from real account reads and actual local/public transport checks.
Evidence: `artifacts/vaani-current-account-check-20261107.json`,
`artifacts/vaani-container-credential-audit-refreshed-20261107.json`,
`artifacts/vaani-config-recheck-tests-20261107.xml`,
`artifacts/vaani-connection-failure-local-20261107.json`,
`artifacts/vaani-connection-failure-public-20261107.json`.


**Latest operational checkpoint, 2026-11-07:** corrected/rebuilt local Docker, applied 011–013
after an encrypted database backup, verified local and actual Quick Tunnel ingress, and
prepared independent V2b browser/deadline controls. **958 backend unit / 53 PostgreSQL /
14 media mock / 23 frontend contract tests passed.** Customer calls, BYOL activation and
billing remain disabled; Vaani authentication and owned-agent acceptance remain blocked.
See [the Docker/tunnel report](docs/VAANI_DOCKER_TUNNEL_REPORT.md) for exact reachable URLs,
changed files, actual evidence and manual steps. This supersedes older no-public-host notes.

**Current checkpoint, 2026-11-07: V2a backend code implemented and contract-tested;
live acceptance blocked.** See [V2a implementation details](docs/VAANI_V2A_IMPLEMENTATION_REPORT.md)
and [dashboard setup guide](docs/VAANI_V2A_SETUP.md). The configured key returned HTTP 401 on
a read-only authenticated probe. No real call, paid subscription or deployment was enabled.
The historical V1 report below remains evidence for that phase; its unimplemented-adapter,
missing-local-secret and schema-head-012 statements are superseded by the V2a report.

## Historical V1 closure

Updated 2026-11-06. Scope: V1 mock lifecycle hardening against FS-VOICE-001 and TS-VOICE-001. V2 real audio, provider reconciliation and billing remain gated.

## Outcome and status vocabulary

- **IMPLEMENTED / TESTED:** durable mock start intent, consistent locks, user/operation-scoped idempotency with normalized digests, independent expiry/recovery, transactional settlement, database integrity constraints, explicit demo consent/revocation, readiness integration and compatible frontend controls.
- **MOCKED:** provider activation, speech answers and elapsed usage. The exact `MockVoiceProvider` has no network or media effects. Every answer remains a fixed fictional fixture; no real policy/case data or conversation is accepted.
- **BLOCKED for live acceptance:** no configured development agent ID, webhook secret, BYOL credentials/endpoint or verified HTTPS/WSS staging setup. API key presence is confirmed; authenticity/permissions were not tested.
- **NOT IMPLEMENTED:** Vaani adapter, browser WebRTC/LiveKit, signed Vaani/billing receivers, BYOL server, actual provider stop/reconnect, paid subscription periods, real policy tools/calculator scenarios, transcripts/recaps and human transfer.

No LangGraph node/edge, insurance knowledge base, report output, approval, human-review decision or delivery hold was changed. Clerk remains the identity provider. No live call, paid checkout, provider account mutation or deployment occurred. Existing uncommitted work was preserved; this session did not commit or push.

## Implementation and audit findings

### Locking and transaction boundaries

All lifecycle mutations use `VoiceSessionService` and acquire entitlement first, followed by sessions in UUID order and operation/ledger records. End never takes the session lock before entitlement. Consent revocation uses the same entitlement lock before changing its receipt and terminating synthetic sessions. Recovery discovers candidates without locks, then takes the entitlement with `SKIP LOCKED` before session mutations. Multiple API workers/recovery processes can share the same durable state.

V1 has one existing entitlement period per user; it has no separate period table or paid rollover. The service does not reset/overwrite that period. Paid period history and funding-period binding are V4 work. A call reservation is capped at its entitlement period end.

A start transaction reserves allowance and persists a `reserved` session and start receipt before adapter activation. The adapter runs outside the database transaction. A second transaction activates the same session only if it is still reserved, consented and within deadline. Cancellation, expiry or revocation during activation cannot reactivate it.

### Idempotency and compatibility

Migration 012 adds durable `voice_operations` keyed by `(user_id, operation, request_key)`. Canonical SHA-256 digests use normalized, validated request fields; default and explicit English have the same start digest. Conflicting language or end-target reuse returns 409. Two customers may use the same UUID independently; start and end have separate namespaces. Start retries return the existing pending/active/terminal session and never redispatch it.

The existing start body is preserved. Empty end bodies remain valid: the session UUID supplies the implicit end operation key. An optional explicit end key is supported and validated by the backend and BFF. Repeated ends, expiry and recovery use the same unique per-session settlement/release operations. Receipt truth is the linked durable session state, not an in-memory success flag.

New security behavior: starting a synthetic session requires explicit `voice_demo` consent. The purpose states that only synthetic session/simulated-usage metadata is stored. It grants no microphone, vendor-processing, transcription or summary permission. The demo's explicit agree/start action records this purpose; withdrawal closes pending/active mock sessions in the consent transaction. Old active sessions without this new consent cannot produce further demo turns; cleanup still works. Historic receipts are not relabeled.

### Expiry, crash recovery and simulated usage

`expires_at` and `recovery_after` are persisted. An independent recovery loop starts with FastAPI, runs immediately and then every configured interval (default 5 seconds), and resumes from database deadlines after restart. The same code is a separate CLI: `python -m app.voice.recovery`, or `--once` for an external scheduler. Recovery works even when provider mode is disabled, but only for rows whose provider is `mock`.

A process killed after committing a start intent leaves its reservation and receipt intact. After the 30-second mock activation lease, recovery marks it failed, settles zero simulated seconds and releases the reserve. A normal mock exception also records failed state and releases once. A process killed during an uncommitted end rolls back; the previously committed reservation remains available to subsequent recovery.

Active mock expiry settles bounded simulated elapsed seconds and releases the unused part. Explicit end, expiry, duplicate requests and worker races cannot add another settlement. Elapsed display is bounded by expiry/terminal time. These are fictional test minutes, not provider duration, customer charges or proof of media termination. A non-mock row is not refunded, ended or displayed as a confirmed mock by this service; it requires provider reconciliation.

Opportunistic deadline checks remain as a defense on reads/starts/turns, but they are no longer the expiry mechanism. No background work is needed from the browser for durable cleanup. Prototype UI polling updates the visible state; media/network reconnection remains unimplemented.

### Database integrity and rollout

Additive `012_voice_lifecycle` preserves 011. It backfills old session digests/deadlines and start receipts without changing original identity, consent snapshots or usage. It removes global session-key uniqueness in favor of user scoping. Constraints enforce nonnegative balances, allowance bounds, valid periods/caps, per-session consumption bounds, valid ledger types and one reservation/settlement/release per session.

Ledger history is immutable. Deferred database checks validate final entitlement totals against ledger sums, session consumption/reservations against ledger entries and ledger ownership. Session owner/key/request digest/reservation are immutable. Invalid existing history makes migration fail rather than silently repair it. Services also reconcile totals before/after mutations and do not clamp corrupt balances to zero.

Downgrade refuses if valid cross-user key reuse would violate the old global constraint; financial history is not deleted to force a rollback. Runtime preflight/readiness now require schema head 012. `/ready` also requires a live, healthy recovery loop; repeated recovery/database failure leaves pending work durable and marks readiness unavailable. Existing development/production databases were not migrated in this task; the migration was exercised only in disposable databases. Deploying this code requires the normal backed-up `alembic upgrade head` process before serving it.

## Files changed in this task

| Area | Files |
|---|---|
| Service and recovery | `backend/app/voice/service.py`, `backend/app/voice/recovery.py` (new); existing provider interface reused |
| Database | `backend/alembic/versions/012_voice_lifecycle.py` (new), `backend/app/models/db/voice.py`, `backend/app/db/schema.py` (new) |
| APIs and consent | `backend/app/api/v1/voice.py`, `backend/app/api/v1/consent.py`, `backend/app/core/consent.py` |
| Runtime/deployment | `backend/app/main.py`, `backend/app/core/config.py`, `backend/.env.example`, `backend/app/ops/readiness.py`, `backend/app/ops/preflight.py` |
| Frontend compatibility | `frontend/components/product/VoiceDemo.tsx`, `frontend/lib/api-client.ts`, `frontend/lib/api-contracts.ts`, `frontend/app/api/backend/[...path]/route.ts` |
| Tests | `backend/tests/integration/test_clerk_identity.py`, `backend/tests/unit/test_production_operations.py`, `frontend/tests/api-contracts.test.cjs`, `frontend/tests/clerk-integration.test.cjs` |
| Documentation | This report, paired specs, `VOICE_ARCHITECTURE.md`, `VOICE_PROVIDER_RESEARCH.md`, `BILLING_ENTITLEMENTS_SPEC.md`, `PROGRESS.md` |

The rest of the prior Clerk/V1 work remains uncommitted as before. Migration 011, provider credentials and environment secret files are unchanged.

## Requirement audit: FR01-FR25

These statuses apply to the full functional requirement, not merely its mock subset.

| Requirement | Actual status after this task |
|---|---|
| FR01 | TESTED for synthetic Clerk-token backend ownership and mock session APIs; genuine Clerk-account/browser journey still pending |
| FR02 | MOCKED: visible AI/fictional disclosure exists; actual spoken disclosure not implemented |
| FR03 | IMPLEMENTED/TESTED separate demo consent and no accidental audio-purpose grants; real microphone/vendor processing consent enforcement awaits V2 |
| FR04 | IMPLEMENTED/TESTED mock revocation, including a pending start; real audio/vendor deletion propagation not implemented |
| FR05 | Prototype entry exists for released reports; production case-bound voice entry/capability handling not implemented |
| FR06 | NOT IMPLEMENTED: no microphone or device access |
| FR07 | MOCKED start/end/state/timer controls; no mute, listening or speaking states |
| FR08 | NOT IMPLEMENTED: fixed prompts, no natural follow-ups/audio interruption/captions |
| FR09 | MOCKED language labels only; no speech-quality acceptance |
| FR10 | IMPLEMENTED/TESTED mock recovery, stable retries and deadlines; no WebRTC reconnect or real provider termination |
| FR11 | Synthetic evidence label only; verified policy tools and production citations not implemented for voice |
| FR12 | Fixed fictional co-payment example only; real policy-topic explanation not implemented |
| FR13 | No case comparison reaches the mock; real sourced comparison speech not implemented |
| FR14 | NOT IMPLEMENTED: no claim-expense simulator. Existing sizing code has unverified development assumptions and is not exposed as one |
| FR15 | MOCKED not-verifiable response; no actual sales-statement verification |
| FR16 | V1 rejects case context/freeform input and sends no held content; real multi-channel hold/source-revocation enforcement awaits V3 |
| FR17 | Mock cannot request/decide a review. Existing human review remains separate; voice request/transfer not implemented |
| FR18 | Existing text/review access unchanged; subscription-independent voice escalation not implemented/tested as a voice journey |
| FR19 | NOT IMPLEMENTED: no plans, price, checkout or renewal promises |
| FR20 | IMPLEMENTED/TESTED mock quota/concurrency/reservation; no paid subscription authority |
| FR21 | TESTED expired mock periods block starts without reset; paid cancellation/renewal/rollover not implemented |
| FR22 | IMPLEMENTED/TESTED crash-safe mock receipts and single settlement/release; provider billing events/reconciliation not implemented |
| FR23 | No audio/transcript/summary stored. Consent-based real recap/history not implemented |
| FR24 | Responsive existing prototype code and build/static checks; actual-device, keyboard and screen-reader acceptance not executed in this task |
| FR25 | TESTED mock failures, safe state/error boundaries and recovery readiness; live provider metrics/errors await V2 |

## Acceptance audit: AC01-AC23

| Criterion | Evidence / remaining boundary |
|---|---|
| AC01 | TESTED anonymous API rejection; private route protection retained, no new genuine-account browser run |
| AC02 | TESTED mock cross-owner reads/end/turn/active; no connection/summary endpoint exists to claim tested |
| AC03 | NOT IMPLEMENTED spoken disclosure; visible mock text retained |
| AC04 | TESTED missing/revoked demo purpose and pending-start revocation; real audio processing/retention not implemented |
| AC05 | NOT IMPLEMENTED microphone/device flow |
| AC06 | TESTED mock end only; mute/interruption and actual audio cessation not implemented |
| AC07 | NOT TESTED actual speech languages |
| AC08 | TESTED separate-process mock start/end crash recovery and stable receipts; no media reconnect |
| AC09 | NOT IMPLEMENTED verified policy turn/citation pipeline |
| AC10 | NOT IMPLEMENTED claim-scenario capability; fictional fixture is not acceptance |
| AC11 | NOT IMPLEMENTED source-based sales-statement checker for voice |
| AC12 | TESTED mock cannot accept another case/context; full held speech/captions/recap and mid-turn revocation await V3 |
| AC13 | NOT IMPLEMENTED voice human-transfer/review-request journey |
| AC14 | NOT TESTED as a voice journey; no voice billing gate added to existing review |
| AC15 | NOT IMPLEMENTED billing state/checkout |
| AC16 | TESTED real parallel PostgreSQL mock reservations, same/conflicting key races, stable operation records |
| AC17 | TESTED expired mock period admission; paid periods/cancellation not implemented |
| AC18 | TESTED duplicate mock end/expiry/recovery and rollback; no signed provider/billing events yet |
| AC19 | TESTED demo does not grant audio/transcript/summary purposes; real artifact storage/deletion not implemented |
| AC20 | NOT TESTED actual device/accessibility journey |
| AC21 | TESTED bounded synthetic adapter failure/invalid payload boundaries; real Vaani outage and voice jailbreak checks await V2/V3 |
| AC22 | MOCKED demo status/allowance; real owned-case entry and held-case assistance await V3 |
| AC23 | NOT IMPLEMENTED commercial subscription disclosure/payment |

## Executed validation

The final integration pass and regression checks completed successfully. Test credentials/databases were disposable and separate from application data. No tests called Vaani or used real insurance policy data.

- Full backend unit suite: **879 passed** in the offline Linux image, network disabled, source mounted read-only, dotenv-blocking launcher. Includes two added recovery-readiness failures. Receipt: `artifacts/voice-v1-unit-20261106.xml`.
- PostgreSQL integration: **37 passed**; receipt `artifacts/voice-v1-postgres-20261106.xml`; includes migrations 001-012 with existing 011 voice rows, parallel start/end/recovery, actual observed lock waits, conflicting/normalized keys, user/operation scoping, consent revocation during start, worker-only expiry including a continuous separate process with live mode disabled, killed start/end subprocesses, immutable history and deferred integrity constraints.
- Frontend: **23 contract/SDK-boundary tests passed**; TypeScript, changed-file ESLint and production Next.js build passed.
- Changed-file Ruff and eight-module mypy passed. The expanded Windows check lacked the declared Postgres checkpoint module; the complete eight-module check passed in the existing Linux runtime image, without changing dependencies. `git diff --check` passed.
- Alembic CLI: clean upgrade to head, downgrade to 011 and upgrade back to 012 passed in a separate disposable database. Migration 011 itself was not edited.

Cleanup: the disposable Postgres container and both temporary databases were removed. Existing application databases and services were left unchanged. Document links, all 25 requirement rows and all 23 acceptance rows were checked.

The earlier 28/33/36 integration and 877 unit results are intermediate/historical; use final receipts below. No real WebRTC, language-quality, paid subscription, human approval or production authorization is inferred from these results.

## V2a readiness: current evidence and manual setup

Public docs and the PyPI wheel were inspected again on 2026-11-06 without installing/executing vendor code or making authenticated Vaani calls. Browser fetch failed; direct HTTPS markdown fetches succeeded. `vaani-sdk==0.3.1` wheel SHA-256: `b6d2e2682d6df6abbb427b28ecb4f0dc48edeac1cfdd3c52daa83d70ce075c3a`. Static source confirms sync/async dispatch and managed sessions; dependency/API compatibility still needs V2 tests.

| Item | Exact readiness | Manual input/action |
|---|---|---|
| `VAANI_API_KEY` | PRESENT, authenticity/scopes unverified; no value printed | Confirm this is the intended development workspace key privately |
| Development agent ID | NOT CONFIGURED | Supply/configure an owned development agent ID with the chosen voice/STT/TTS stack |
| `VaaniVoiceProvider` | NOT IMPLEMENTED; mock interface/service ready | No manual code action; implement contract tests/adapter in V2a |
| WebRTC/LiveKit | NOT IMPLEMENTED or live-tested | Allow intended browser origin in the development agent; confirm deployed client/server contract |
| Signed webhook receiver | NOT IMPLEMENTED; HMAC contract publicly documented | Configure an independent webhook secret and reachable HTTPS callback when implemented |
| Authenticated BYOL | NOT IMPLEMENTED; protocol/source docs reviewed | Set dedicated Bearer credential and WSS endpoint; disable platform fallback in the owned agent |
| Provider hard termination | NOT VERIFIED; mock expiry proves nothing about audio stop | Verify direct-dispatch cap/forced end, or deliberately select managed sessions and prove `explicit_end` on that same lifecycle |
| HTTPS/WSS staging | NOT VERIFIED; no staging URL/BYOL URL found in checked configuration names | Confirm backend hostname, TLS, WebSocket support, allowed origins and webhook reachability |
| Paid subscriptions | DISABLED/NOT IMPLEMENTED | Merchant/provider/prices/cost review is later V4 work |

Current dispatch reference uses `token`, `room_name`, `connection_url` and optional `live_captions_url`; do not assume pasted aliases. Current webhook guide states seconds for both terminal durations and raw-body HMAC-SHA256 with event-family-specific signature formatting. The SDK managed session API uses distinct `session_token` -> `lk_token`/`lk_url`, with explicit disconnect. Static SDK source also uses `/api/call_details/` while the supplied guide names `/api/call-details/{id}`: verify that method against the live contract before using it rather than assuming equivalence. These are documentation/source observations, not account acceptance.

**V2a can begin with disabled adapter/contract-test work after this V1 review. A real synthetic call cannot yet pass its gate.** Agent/setup, signed event delivery, audio termination and staging evidence must be closed first. Do not enable paid/live features merely because V1 is complete.

Sources: [dispatch](https://docs.vaani.dev/api-reference/trigger-call), [webhooks](https://docs.vaani.dev/guides/webhook-setup), [SDK](https://docs.vaani.dev/sdk), [BYOL](https://docs.vaani.dev/guides/byol), [PyPI metadata](https://pypi.org/pypi/vaani-sdk/json). Paired specs remain the behavior/architecture contract; later phase work requires its own tests and acceptance.
