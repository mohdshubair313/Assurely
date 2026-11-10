# Docker, Quick Tunnel and V2b preparation checkpoint

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


Verified 2026-11-07. Local development only; no production deployment, customer call,
paid subscription or real Vaani call was enabled. Existing application data was preserved.

## Actual service addresses

| Service | Address | Observed result |
|---|---|---|
| Local FastAPI | `http://localhost:8000/health` and `/ready` | Both HTTP 200 |
| Existing Quick Tunnel | `https://numerical-devon-locate-spaces.trycloudflare.com/health` and `/ready` | Both HTTP 200 after fixing the origin |
| Public webhook | `https://numerical-devon-locate-spaces.trycloudflare.com/v1/webhooks/vaani` | Invalid signature 401; locally signed synthetic receipt 200; identical retry deduplicated |
| Public BYOL base | `wss://numerical-devon-locate-spaces.trycloudflare.com/v1/voice/provider/byol` | WebSocket upgrade attempts reach the origin and return 403 for unauthorized/unknown calls; **no authenticated 101/audio acceptance** |

Vaani appends `/<call_id>` to the BYOL base. The Quick Tunnel process was already running
against `http://localhost:8000`; its previously reported hostname was actually tested and
reused, not assumed active. No additional tunnel was necessary. It stops working if that
process stops, and a new Quick Tunnel normally receives another hostname. This is temporary
development reachability, not a stable staging deployment or availability promise.

## Docker root cause and fix

The checked-in base Compose already declared `127.0.0.1:8000:8000`. There was no additional
Compose override and no `COMPOSE_FILE` environment override. Actual container inspection
showed `insurance-api` had **no connected networks and no published host port**, despite
being reported running. Its old October image had current `app/` bind-mounted, so some
source was fresh, but dependencies and baked migration/tool files were not established as
current. Container age alone was not the diagnosis.

Added explicit `docker-compose.voice-dev.yml` and built `insuranceai-api:voice-dev` using
the development Dockerfile plus the existing tested runtime constraints. Runtime Python is
**3.11.17**, Clerk SDK **7.1.0**, asyncpg **0.31.0**, Uvicorn **0.54.0** and websockets
**16.1.1**. `pip check` passed. Hashes of seven installed/mounted voice/worker modules match
current workspace source. API application, migration and tool binds are read-only. The worker
also reads the current application mount. Later preparation changes are visible through these
mounts; a portable deployment still needs its own fresh immutable image.

Only application services were recreated/restarted. Compose also removed two obsolete
application-container duplicates bearing the same API service labels. PostgreSQL, Redis,
Chroma and their named volumes were not recreated or removed. The temporary port-8080
workaround was stopped; the canonical API now uses localhost port 8000. Uvicorn listens on
`0.0.0.0:8000` inside its container, without access logs/reload, with bounded WebSocket frames
and concurrency. The host binding remains `127.0.0.1`, not all interfaces.

## Backup, migrations and data integrity

Before migration, created an AES-256-GCM encrypted custom PostgreSQL dump in ignored
`.local/database-backups/`, with a separate private local key and JSON manifest. Windows
directory permissions are restricted to the current user. The archive was decrypted only
in memory and successfully read with `pg_restore --list`; plaintext was not written to disk.
This is a verified readable local rollback checkpoint, **not a full restore drill or off-host
production backup**. Keep the key and archive private; both are currently local.

Applied the existing migrations through Alembic:

`010_clerk_identity -> 011_voice_entitlements -> 012_voice_lifecycle -> 013_vaani_backend`.

No applied migration was edited and no database was dropped/recreated. Existing table counts
were identical before/after: 98 users, 100 sessions, 3 policy-term rows and 3 consent rows.
Current application schema is **013**. Voice sessions, entitlements and ledger entries remain
zero in this application database; only minimized synthetic transport-probe receipts were added.
They are intentionally retained by the immutable event audit policy.

## Recovery and safe deadline handling

Added separate Compose `voice-recovery` service using the existing recovery loop. It has a
private health receipt and Docker healthcheck, restart policy and no published port. The API's
existing recovery loop remains active too; locks/idempotency support concurrent workers.
Actual worker restart passed: a new process resumed successful database passes and refreshed
its healthy receipt. API restart returned readiness 200. Redis PING and Chroma heartbeat passed.

V2b preparation now detects expired server-owned **synthetic Vaani** bindings and persists
`termination_required` after entitlement -> session -> binding locks. It does not infer call
termination, change the session to ended, call a provider, debit usage or release reservations.
Signed events are processed before deadline marking. Repeated workers/restarts do not enqueue
duplicate deadline work, and a later valid signed terminal event can still settle once.
**A durable deadline marker is not a verified provider media stop or spending cap.** Actual
termination/status orchestration remains blocked work, as does uncertain dispatch recovery.

## Public ingress security

The voice-development override enables only the signed event receiver. Customer voice remains
`VOICE_PROVIDER=disabled`; dispatch, BYOL activation and agent-reviewed flags remain false.
Billing has no enabled adapter/checkout. No microphone/customer policy data was sent externally.

`TUNNEL_INGRESS_ONLY=true` restricts the whole port-8000 API to exact health/readiness,
signed-webhook, BYOL socket and read-only `/v1/me` contracts. Documentation, admin, customer
voice and other mutations are blocked. `/v1/me` requires the separate private gateway secret
**and** underlying Clerk identity. Caller-controlled forwarding headers cannot remove this
boundary. If customer provider/dispatch is enabled in this profile, it fails closed.

Fixed an audited slow-body issue: the webhook now rejects malformed signature headers and
invalid/oversized Content-Length before body processing and enforces a five-second body-read
deadline, while retaining the streamed byte cap and mandatory raw-body HMAC. It never accepts
an unsigned production event. Raw transcript/summary/phone data is not stored in the inbox.

The public/local probes each passed twelve checks. Actual signed synthetic receipt digests
were found durably in Postgres with `unmatched` status; unknown rooms cannot grant ownership
or mutate usage. These signatures were generated by our probe, **not delivered by Vaani**.
Runtime logs and captured HTTP responses contained none of the checked configured secrets.
BYOL remains closed: a 403 handshake rejection proves reachability/rejection, not a successful
authorized WebSocket connection. Do not change flags or create a fake agent approval to obtain 101.

## Vaani blockers investigated separately

- Correct setting is `VAANI_API_KEY`; fixed official origin is `https://api.vaanivoice.ai`;
  authentication is server-side `X-API-Key`, not a BYOL token or Bearer-form master key.
- Local key is present, matches the documented prefix, and has no surrounding whitespace,
  control character or accidental Bearer prefix. No process-level Vaani variable overrides
  were found. The extra local `VAANI_BYOL_BEARER_TOKEN` name is not consumed: the supported
  name is `VAANI_BYOL_TOKEN`. Its placeholder was not substituted for the valid private token.
- One bounded, read-only account preflight in this task still returned the sanitized
  `authentication` failure. The earlier directly observed HTTP 401 remains the evidence for
  the reported status; the adapter groups 401/403 without exposing vendor bodies. No retry
  storm, alternate-header guessing, agent mutation or call was attempted.
- `VAANI_AGENT_ID` is a placeholder rather than a UUID. It cannot cause the account-list 401,
  because that read-only request does not include an agent ID. Ownership cannot be verified
  while account authentication fails. No agent UUID was fabricated or silently selected.
- Expiry/revocation, workspace mismatch, role/scopes or account provisioning cannot be diagnosed
  conclusively without the owner's dashboard. A local formatting/header fix does not resolve them.

## Independent V2b implementation

Pinned official LiveKit client, typed/injected media controller, authorization heartbeats,
microphone permission and mute/playback controls, muted same-session reconnect, safe consent
withdrawal/stale-operation cleanup, and reusable CreateUI controls. They are **unmounted** and
require future authenticated server connection material; the existing mock remains text-only.
Browser disconnect does not dispatch another call, mark provider-ended or release usage.
Full details: [browser preparation report](VAANI_V2B_BROWSER_PREPARATION.md).

NOT IMPLEMENTED/NOT VERIFIED: complete real dispatch/binding coordination, authenticated
browser connection/refresh contract, real BYOL 101, LiveKit/Vaani audio interoperability,
provider hard-stop/status evidence, actual language/device/latency testing, grounded insurance
speech, consent-stop propagation to the real provider, subscriptions and billing.

## Validation and evidence

| Check | Actual result |
|---|---|
| Backend unit regression in rebuilt image | **958 passed**; `artifacts/voice-docker-tunnel-unit-20261107.xml` |
| Fresh disposable PostgreSQL 16 integration | **53 passed**; migrations 001–013, concurrency/restart/ledger/consent/BYOL and deadline retention; `artifacts/voice-docker-tunnel-postgres-20261107.xml` |
| Independent security review | **79 focused offline checks passed**, no unresolved security regression in the reviewed scope |
| Frontend media mocks | **14 passed** |
| Existing frontend contracts | **23 passed** |
| Frontend TypeScript, targeted ESLint, production build | Passed |
| Runtime dependency audit | **0 vulnerabilities**; full audit retains 8 moderate development-tooling advisories |
| Changed backend Ruff and eight-module mypy | Passed |
| Local HTTP/auth/signature/WS rejection checks | **12 passed**; `artifacts/voice-ingress-local-20261107.json` |
| Public HTTPS/signature/WS rejection checks | **12 passed**; `artifacts/voice-ingress-public-20261107.json` |
| Runtime hashes/dependencies/data/receipt checks | Passed; `artifacts/voice-local-runtime-20261107.json` |
| Separate worker actual restart | Passed; `artifacts/voice-worker-restart-20261107.json` |

The first targeted auth test omitted its synthetic Clerk configuration and correctly received
503; fixed that test setup. The first new deadline concurrency assertion counted another
deliberately expired shared fixture; drained its marker before measuring the new case, then
reran the fresh-database suite to 53 passing. One ingress-tool kwargs typing annotation was
corrected. No auth, consent, phase or financial control was weakened. The updated pytest-asyncio
tooling emits a fixture-loop-scope deprecation warning; tests pass without changing runtime behavior.

## Files changed in this checkpoint

| Area | Files |
|---|---|
| Docker | New `docker-compose.voice-dev.yml`; base Compose/Dockerfiles inspected and preserved |
| Ingress | New `backend/app/ops/tunnel_boundary.py`; `backend/app/main.py`, `backend/app/core/config.py`, `backend/.env.example`, `backend/app/api/v1/vaani.py` |
| Worker/deadlines | New `backend/app/ops/voice_worker.py`, `backend/app/voice/deadlines.py`; existing `backend/app/voice/recovery.py` |
| Operator tools | New `backend/tools/backup_local_database.py`, `backend/tools/verify_voice_ingress.py`, `scripts/start-voice-tunnel.ps1`; updated `backend/tools/vaani_preflight.py` |
| Backend tests | New `backend/tests/unit/test_tunnel_operations.py`, `backend/tests/unit/test_voice_provider_deadlines.py`; extended `backend/tests/integration/test_clerk_identity.py` |
| Browser preparation | New `frontend/lib/voice/controller.ts`, `frontend/lib/voice/livekit-room.ts`, `frontend/components/product/VoiceAudioControls.tsx`, `frontend/tests/voice-media.test.cjs`; updated `frontend/package.json`, `frontend/package-lock.json` |
| Reports | This report, new `docs/VAANI_V2B_BROWSER_PREPARATION.md`, setup/paired specs, root implementation/provider-research reports, `PROGRESS.md` |

Earlier accumulated uncommitted Clerk/V1/V2a changes were preserved. Private `.env`, encrypted
database backup/key and runtime receipts remain ignored; no credentials were committed.

## Exactly what the owner needs to do next

1. In **Vaani Dashboard -> Developers -> API Keys**, select the intended development workspace.
   Verify your workspace membership/API access, key status/expiry and permissions. Copy a valid
   workspace API key privately into `backend/.env` as `VAANI_API_KEY`. Do not paste it in chat.
2. Open the saved development agent in that **same workspace** and copy its **Agent ID UUID**
   from Overview into private `VAANI_AGENT_ID`. The display name and a dashboard URL are not IDs.
3. Set BYOL base to the actual WSS URL above, use the current private `VAANI_BYOL_TOKEN` in
   its token field, and save **No fallback**. Configure the exact webhook URL above with the
   current private `VAANI_WEBHOOK_SECRET`. Current flags intentionally keep BYOL closed;
   dashboard connection testing may reject until a valid server-owned call/gate exists.
4. Confirm the selected fictional development agent's voice/STT/TTS, no-fallback and recording/
   retention behavior. Then rerun **one** read-only preflight. Recreate application services
   after changing private environment variables; no database service recreation is required.
5. After credential/agent acceptance, implement controlled dispatch/binding and verified provider
   termination before a deliberately authorized fictional call. A stable HTTPS/WSS staging host
   remains necessary beyond the temporary Quick Tunnel.

Private token-copy commands and dashboard field mapping remain in [the setup guide](VAANI_V2A_SETUP.md).
**V2a live acceptance is incomplete. V2b independent code preparation has progressed; actual
provider/audio acceptance remains blocked.** No permission for customer calls or paid billing
is implied by these infrastructure results.

## Reproduce and rollback safely

From the repository root, with Docker Desktop running:

```powershell
docker compose -f docker-compose.yml -f docker-compose.voice-dev.yml build api
python backend/tools/backup_local_database.py
docker compose -f docker-compose.yml -f docker-compose.voice-dev.yml run --rm --no-deps api python -m alembic upgrade head
docker compose -f docker-compose.yml -f docker-compose.voice-dev.yml up -d --no-deps --no-build api voice-recovery
```

Use `backend\venv\Scripts\python.exe` instead of `python` if the host interpreter lacks the
declared dependencies. `scripts/start-voice-tunnel.ps1` starts a **new** hidden Quick Tunnel only
after local readiness and exposure checks; it reports a URL but does not claim public verification.
The existing tunnel was reused in this checkpoint. To run repeatable ingress checks, from `backend`:

```powershell
venv\Scripts\python.exe -m tools.verify_voice_ingress --base-url http://localhost:8000
venv\Scripts\python.exe -m tools.verify_voice_ingress --base-url https://numerical-devon-locate-spaces.trycloudflare.com
venv\Scripts\python.exe -m tools.vaani_preflight --offline
```

Without `--offline`, preflight performs bounded read-only Vaani requests; do not poll it in a loop.
The verification script writes only fictional event metadata; its HMAC/key values never print.

Rollback means stop the known Quick Tunnel first, keep dispatch/customer voice disabled,
continue reconciliation, and use a compatible schema-013 application version. Do not downgrade,
drop volumes or restore the database merely to make an old container appear ready. Before
returning to unrestricted private development Compose, verify the public tunnel is stopped.
The voice-only profile intentionally blocks the ordinary frontend API journey while exposed.

Sources checked: [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/),
[WebSocket transport](https://developers.cloudflare.com/network/websockets/),
[Vaani auth/reference](https://docs.vaani.dev/api-reference/introduction),
[agent ID](https://docs.vaani.dev/getting-started/create-agent),
[signed webhooks](https://docs.vaani.dev/guides/webhook-setup),
[BYOL](https://docs.vaani.dev/guides/byol).
