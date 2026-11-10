# V2a implementation report: Vaani backend integration

**2026-11-08 implementation update:** managed lifecycle APIs/worker, mounted private LiveKit
development UI, current-report/follow-up evidence tools, consented encrypted report excerpts,
signed test billing and gated test-period spending/rollover are implemented. Customer calls
and paid billing remain disabled. This does not close live-provider or all V3?V5 acceptance.
The earlier 401/invalid-agent and unmounted-control statements are historical; account reads
passed on November 7. See [the phase implementation checkpoint](VAANI_PHASES_IMPLEMENTATION_20261108.md)
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


**Operational follow-up:** [Docker/tunnel verification and V2b preparation](VAANI_DOCKER_TUNNEL_REPORT.md)
now records the rebuilt local runtime, backed-up application migration to 013, verified
temporary public HTTPS ingress and newer tests. Vaani authentication/agent and actual
BYOL 101/audio acceptance remain blocked. The original implementation checkpoint below
is historical where its no-public-host/application-not-migrated statements are superseded.

2026-11-07. Contract: FS-VOICE-001 / TS-VOICE-001. Scope: backend provider adapter,
authenticated provider ingress and synthetic lifecycle preparation. V1 remains intact.

**Outcome: feasible backend work implemented and tested. Real-provider acceptance is BLOCKED.**
The configured API key returned HTTP 401 to a read-only agent-list request; the configured
development agent ID is invalid and a verified staging hostname is missing. No real call, paid billing,
agent configuration mutation, customer enablement, deployment, commit or push occurred.

## Implemented behavior

### Bounded server-side provider adapter

`VaaniVoiceProvider` uses the existing Python/httpx architecture, fixed
`https://api.vaanivoice.ai` origin and private `X-API-Key`. Requests/responses are typed and
bounded; redirects are disabled, errors are sanitized and a timed-out dispatch is never
automatically retried. Agent UUID ownership is checked against the authenticated detail
endpoint before dispatch. Listing uses the SDK's documented/source-inspected `/api/agents`;
the preflight reports the first page only, not a fabricated whole-account inventory.

Dispatch requires all four explicit development gates, a development/staging environment,
HTTPS staging origin, configured secrets, a UUID reference and English/Hindi language code.
Runtime overrides request BYOL with fallback `none`; saved dashboard configuration still
requires manual confirmation because these fields are write-only in GET responses. Public
docs describe deep-merging nested overrides; actual account application is unverified.
Returned `token`, `room_name`, `connection_url` and optional `live_captions_url` are validated.
Connection hosts are restricted to documented Vaani media hosts. Access/captions secrets
are excluded from dataclass representations. No master key reaches Next.js or the browser.

**This adapter is not connected to customer session creation.** Selecting Vaani through the
existing customer API remains unavailable. No automatic startup probe or dispatch occurs.
An HTTP response fixture proves parsing, not that a real provider accepted a call.

### Signed durable provider event receiver

`POST /v1/webhooks/vaani` is closed by default and independently authenticated with a mandatory
raw-byte HMAC-SHA256 signature. It accepts exactly one `X-Webhook-Signature` header and bounded
JSON, rejects duplicate JSON fields, malformed call identifiers, invalid timestamps and
nonfinite/negative durations. Lifecycle signatures are bare hex; postprocessing uses
`sha256=` as currently documented. Current duration units are seconds for both families.

Acknowledgement follows database commit. The inbox stores an immutable digest, event type,
room, timestamp and duration, plus processing status/reason. It discards raw bodies,
transcripts, phone numbers, summaries, request overrides and tokens. Identical byte retries
deduplicate by digest; separately encoded terminal events cannot debit a settled session again.
Events outside a 300-second past / 30-second future window are durably quarantined, not applied.
Legitimate deliveries outside this window need operator reconciliation, not an auth bypass.

Workers lock entitlement -> session -> provider binding -> receipt -> ledger writes. A
signed `call_ended` for an exact server-owned synthetic binding settles rounded-up seconds
once, bounded by the reservation, releasing the remainder. Unknown calls cannot create a
session or entitlement. Event-before-binding receipts can be requeued and are rediscovered
after a binding exists, including the concurrent-binding race. Delayed starts cannot reopen
terminal sessions. Missing/excess duration, conflicting terminal facts and failures with
uncertain cost retain reservations or mark reconciliation required; they do not imply free usage.
Postprocessing is optional and never the primary settlement source. Human-transfer events
have no approval/release authority.

The existing recovery loop now also processes the durable inbox. The independent
`python -m app.voice.recovery --once` command processes both mock deadlines and provider
receipts after restart, even with new dispatch disabled. Real-call polling, forced termination
and automatic resolution of missing terminal events are **not implemented/verified**.

### Authenticated synthetic-only BYOL preparation

`/v1/voice/provider/byol/{provider_call_id}` verifies a dedicated Bearer credential before a
database lookup. It requires an exact server-owned room/agent binding, active mapped Clerk
identity, allowlisted test user/entitlement, unexpired synthetic Vaani session, no case context,
and current microphone/vendor-processing consent. Unknown/mock/unauthorized calls are rejected.

The socket implements documented config/greeting frames, response-required turns, matching
call/response IDs, bounded messages and heartbeat frames. Every turn/heartbeat rechecks
authorization. PostgreSQL retains a bounded single-connection lease and monotonic response ID;
replays fail closed across reconnects. Clean close releases the lease before the close frame,
with shielded cleanup for ASGI cancellation; a crash/outage falls back to the 20-second lease.
An old connection cannot release a newer lease. This is authorization/replay preparation,
not proof of lossless real-media reconnect or exactly-once audible delivery.

The response is fixed, explicitly AI-disclosed and unavailable for factual insurance advice.
Untrusted transcript/system-role input is ignored and never persisted, echoed or traced.
No LLM, graph node, RAG store, policy tool, calculator, report release or approval is invoked.
There is no local platform-model fallback; genuine vendor no-fallback behavior awaits V2b.

### Integrity, configuration and ingress

Additive migration `013_vaani_backend` creates minimized provider binding/event tables,
nonnegative checks and immutable binding/receipt identity triggers. It does not edit 011 or
012. Existing deferred ledger/entitlement integrity remains authoritative. Audit-bearing
downgrade is refused; empty-table downgrade/upgrade was tested. Runtime schema readiness now
requires 013. No existing application/production database was migrated.

Settings and `.env.example` include API key, agent ID, webhook secret, BYOL token, staging
origin and four closed flags. A helper securely generated distinct development credentials
inside ignored `backend/.env`, without printing them. Final audit found a short configured
webhook value, which was explicitly regenerated locally; its matching dashboard/staging value
must be updated. The agent configuration is present but not a valid UUID, and was not fabricated.
The helper can copy one credential privately
to the Windows clipboard. The read-only preflight exposes sanitized account readiness only.

Production gateway exemption is limited to the exact signed webhook path. Ordinary customer
APIs retain their existing gateway/JWT/owner boundaries. Optional nginx routing adds exact
webhook forwarding and authenticated WebSocket upgrade handling, size/rate bounds and
overwritten forwarding headers. Uvicorn frame and ping limits are explicit. Actual managed
hosting, certificate, ingress logging and plan behavior remain deployment checks.

## Files added or changed for V2a

| Area | Files |
|---|---|
| Adapter and provider contract | `backend/app/voice/vaani.py`, `backend/app/voice/providers.py` |
| Events/BYOL/recovery | `backend/app/voice/events.py`, `backend/app/voice/byol.py`, `backend/app/voice/recovery.py` |
| API boundary | `backend/app/api/v1/vaani.py`, `backend/app/api/v1/router.py`, `backend/app/main.py` |
| Database | `backend/alembic/versions/013_vaani_backend.py`, `backend/app/models/db/voice_provider.py`, `backend/app/models/db/__init__.py`, `backend/app/db/schema.py` |
| Runtime and config | `backend/app/core/config.py`, `backend/.env.example`, `backend/app/ops/serve.py`, `deploy/nginx.conf.template` |
| Operator helpers | `backend/tools/configure_vaani_dev.py`, `backend/tools/vaani_preflight.py` |
| Tests | `backend/tests/unit/test_vaani_backend.py`, `backend/tests/integration/test_clerk_identity.py`, `backend/tests/unit/test_production_operations.py`, `backend/tests/run_offline.py` |
| Documentation | This report, setup guide, paired specs, root implementation/research/architecture documents, `PROGRESS.md` |

Other uncommitted Clerk/V1/frontend work predates this V2a change and was preserved.
Private environment contents are not deliverable source files.

## Requirement and acceptance deltas

The [V1 report](../VOICE_IMPLEMENTATION_REPORT.md) retains all FR01-FR25 and AC01-AC23 rows.
No full audio/product requirement is promoted solely because its backend subset passed.

| Scope | Current status and limit |
|---|---|
| FR01/FR03/FR04; AC01/AC02/AC04 | IMPLEMENTED/TESTED synthetic BYOL identity, active consent, ownership/expiry and revocation controls; genuine Clerk/browser/audio journey pending |
| FR10; AC08 | TESTED durable signed receipt processing in a fresh process and socket lease/replay recovery; live provider termination/reconnect remains pending |
| FR16/FR17; AC12/AC13 | IMPLEMENTED fail-closed synthetic response; transfer events cannot approve reports; actual grounded/held-case speech and human transfer not implemented |
| FR20/FR22; AC16/AC18 | TESTED existing V1 reservation concurrency plus parallel signed-event receipts/workers, duplicate/reordered reconciliation and single settlement; paid provider/billing acceptance not satisfied |
| FR23; AC19 | TESTED minimized event persistence and discarded transcript; consented real recording/summary retention/deletion remains pending |
| FR25; AC21 | TESTED adapter auth/timeouts/host/contract failures, BYOL bad auth/unknown call/replay/consent/identity rejection and fixed safe response; real speech/security/fallback evaluation pending |
| Other FR/AC rows | Prior V1 state unchanged. No new microphone, LiveKit, natural conversation, policy tooling, simulator, subscription or accessibility acceptance claimed |

## Actual validation results

- **917 backend unit tests passed**, offline Linux image, no network, read-only source and
  dotenv-blocking runner. Includes **38 new Vaani contract checks**. Receipt:
  `artifacts/vaani-v2a-unit-20261107.xml`.
- **51 PostgreSQL integration tests passed** on fresh disposable PostgreSQL 16, applying
  migrations 001-013 and preserving existing 011 fixture rows. Includes prior V1/Clerk tests,
  concurrent signed deliveries/workers, reordered/conflicting/uncertain events, unknown/stale
  events, event-before-binding, fresh-process durable recovery, immutable receipts/bindings,
  BYOL handshake/replay/reconnect/revocation, single lease/expiry and disabled/expired/agent
  rejection. Receipt: `artifacts/vaani-v2a-postgres-20261107.xml`.
- **23 frontend contract tests passed**; production Next.js build including TypeScript passed.
  No new browser WebRTC/live-provider test is implied.
- Changed-file Ruff and seven-module strict mypy with imported diagnostics suppressed passed.
  A stale unused type-ignore was removed after mypy detected it.
- Alembic CLI clean upgrade to 013 -> empty downgrade to 012 -> upgrade to 013 passed in a
  separate disposable database. Nginx syntax and dummy TLS certificate loading passed;
  `artifacts/vaani-v2a-ingress-20261107.json`. This is not a deployed WSS handshake.
- Actual read-only Vaani account probe returned **401 Unauthorized**. Adapter preflight
  independently returned sanitized `authentication`, `dispatch_attempted=false`.
  `artifacts/vaani-account-preflight-20261107.json` records the first result without credentials.

The first integration pass exposed a WebSocket lease cleanup race when ASGI cancellation
followed a close frame; fixed cleanup-before-close plus cancellation shielding and verified
reconnect. A later test-only subprocess fixture passed a UUID instead of a string environment
value; corrected the fixture and reran the fresh database suite to the final 51 passing result.
No auth, consent, ledger or signature boundary was relaxed. Mock transports/signed fixture
events are **MOCKED provider evidence**, despite using real PostgreSQL transactions.

Final local-link and credential-preservation/secret scans passed, as did normal repository
`git diff --check`. The owned disposable PostgreSQL container (and its test databases) was
removed; temporary nginx certificate/key/config files were cleaned. Existing application
containers were left running. Sanitized final readiness: `artifacts/vaani-v2a-readiness-20261107.json`.

## Remaining work and V2b readiness

**BLOCKED:** valid development API key, valid owned agent UUID, reachable HTTPS/WSS staging host,
saved no-fallback/retention settings and genuine signed event evidence. The current key's 401
is a real blocker; API key presence is not successful authentication.

**NOT IMPLEMENTED/NOT VERIFIED:** complete controlled real dispatch-to-binding orchestration,
uncertain dispatch/end recovery against vendor status, browser LiveKit/audio controls,
provider hard termination/caps, real consent-stop propagation, language/device evaluation,
voice-scoped verified policy/calculator tools, recaps and paid subscriptions. Pending reservations
without trustworthy terminal evidence remain for reconciliation; mock expiry is never proof
that a provider call ended. No account data/privacy/pricing approvals were fabricated.

V2b implementation can begin from these tested interfaces. **Its real-call acceptance cannot
begin until account/staging gates are resolved and a safe binding/termination harness exists.**
The user must configure the owned agent/key and hosting; generated ingress credentials can
be copied privately using [the dashboard setup guide](VAANI_V2A_SETUP.md). URL formats there
are explicitly not deployed working endpoints. Customer calls and paid billing stay disabled.

Sources checked: [Vaani WebRTC dispatch](https://docs.vaani.dev/api-reference/trigger-call),
[signed webhooks](https://docs.vaani.dev/guides/webhook-setup),
[BYOL protocol](https://docs.vaani.dev/guides/byol),
[SDK](https://docs.vaani.dev/sdk),
[Back4app Containers capabilities](https://www.back4app.com/docs-containers/release-notes).
