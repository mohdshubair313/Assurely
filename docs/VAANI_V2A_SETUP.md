# Vaani V2a development setup

**2026-11-08 implementation update:** managed lifecycle APIs/worker, mounted private LiveKit
development UI, current-report/follow-up evidence tools, consented encrypted report excerpts,
signed test billing and gated test-period spending/rollover are implemented. Customer calls
and paid billing remain disabled. This does not close live-provider or all V3?V5 acceptance.
The earlier 401/invalid-agent and unmounted-control statements are historical; account reads
passed on November 7. See [the phase implementation checkpoint](VAANI_PHASES_IMPLEMENTATION_20261108.md)
for exact completed work, tests, deviations and remaining software/approval gates.


**Current operational checkpoint, 2026-11-07:** Docker API and recovery are healthy on
`http://localhost:8000`; the existing Quick Tunnel below was actually verified. Local database
is migrated through 013 after an encrypted backup. Refreshed container credentials now pass
Vaani authentication and owned-agent validation (both GET requests returned 200).
[Current results and manual actions](VAANI_DOCKER_TUNNEL_REPORT.md)
supersede the earlier undeployed-host notes below. This is temporary development ingress,
not production or successful live-provider acceptance.

Checked 2026-11-07. Local backend and temporary public ingress are verified; live calls remain disabled.
The earlier HTTP 401 and invalid UUID were superseded after refreshing stale container configuration.
No call was created, no agent changed and no subscription activated.

## What to paste in the dashboard

The exact Quick Tunnel URLs below were tested for development reachability. They depend on
the currently running tunnel process and are not stable production addresses. Valid-session
BYOL/audio remains gated. The Vercel frontend domain does not host these Python WebSockets.

| Setting | Exact source/value to use | Current readiness |
|---|---|---|
| Assurely `VAANI_AGENT_ID` | In Vaani, open the owned development agent, save it, then copy **Agent ID** from its Overview. Paste that UUID into the private backend environment, not the browser. | Current local value is not a valid UUID. Agent ownership cannot be checked until the API key authenticates. |
| Agent BYOL WebSocket URL | `wss://numerical-devon-locate-spaces.trycloudflare.com/v1/voice/provider/byol` | Actual tunnel route reached; unauthorized/unknown upgrade attempts return 403. BYOL remains disabled; no valid-session 101/audio claim. Base only; Vaani appends `/<call_id>`. |
| Agent BYOL Auth Token | The actual privately generated `VAANI_BYOL_TOKEN`, copied using the command below. Paste the token only; Vaani adds `Authorization: Bearer ...`. | Generated in ignored local `backend/.env`. It must also be securely configured on the staging backend. |
| Webhook URL | `https://numerical-devon-locate-spaces.trycloudflare.com/v1/webhooks/vaani` | Actual public signed synthetic receipt/deduplication passed. Genuine Vaani delivery is pending. Temporary URL depends on the running Quick Tunnel. |
| Webhook signing secret | The actual `VAANI_WEBHOOK_SECRET`, copied privately using the second command below. Configure the same value on both Vaani and the staging backend. | Generated locally; vendor configuration and a genuine signed delivery remain pending. |

In the development agent's **Brain / Reasoning Language Model / BYOL** settings, select BYOL,
enter the URL and token, and select **No fallback**. Confirm this in the saved agent; a local
boolean or REST request alone does not prove the vendor applied it. Disable vendor cross-call
memory and verify retention/recording behavior before transmitting anything beyond fictional data.

In **Settings / Webhooks**, configure the HTTPS URL and signing secret. Enable lifecycle
events including `call_started`, `call_ended` and call failure events; optional
`call_postprocessing` is handled but never required to settle usage. Human-transfer events are
informational and cannot approve a report. If this workspace's UI does not expose a signing-secret
field, obtain the account-specific setup from Vaani support; never bypass signature verification.

## Copy the development credentials privately

Run from the repository root in PowerShell. These commands copy to the Windows clipboard;
they do not print the secret. Paste only into the intended Vaani dashboard field or hosting
secret store. Clipboard history/sync follows your Windows settings; clear it after use.

```powershell
.\backend\venv\Scripts\python.exe backend\tools\configure_vaani_dev.py --copy byol
```

After pasting the BYOL token, copy the separate webhook secret:

```powershell
.\backend\venv\Scripts\python.exe backend\tools\configure_vaani_dev.py --copy webhook
```

The helper preserves existing credentials and refuses to write an environment file that Git
does not ignore. It does not enable feature flags. The Vaani master API key is a third,
different credential: obtain a valid development-workspace key from **Developers / API Keys**
and update private `VAANI_API_KEY`. Do not paste any of these values into chat, source code,
`NEXT_PUBLIC_*`, screenshots or logs. No working credentials are included in this document.

Final audit found a configured webhook value shorter than the required minimum; it was
explicitly rotated locally with `--rotate webhook`. Copy the current value, not an earlier
dashboard entry. Future deliberate rotation uses `--rotate byol` or `--rotate webhook` and
requires updating the corresponding vendor and staging secret together. Default runs do
not rotate a usable existing value.

## Configuration and deployment order

1. Back up the target PostgreSQL database and apply additive migration `013_vaani_backend`
   using the normal Alembic deployment process. Migration 012 is preserved. Runtime readiness
   requires head 013. The existing local application database is now 013 after an encrypted
   checkpoint; future staging databases still require the normal backed-up migration process.
2. Configure Clerk's existing issuer/identity mapping unchanged. Configure distinct private
   API key, BYOL token and webhook secret, development agent UUID, and
   `VAANI_STAGING_BASE_URL=https://<confirmed-backend-host>`.
3. Deploy the FastAPI container with HTTPS webhook routing, WebSocket upgrades, Authorization
   forwarding, bounded frames and a running durable recovery worker. The optional repository
   nginx template contains the two exact ingress paths; it is not installed on Back4app by
   editing that file. Keep access/body/Authorization logging disabled at your managed ingress.
4. Leave `VAANI_DISPATCH_ENABLED`, `VAANI_INGRESS_ENABLED`, `VAANI_BYOL_ENABLED` and
   `VAANI_DEV_AGENT_REVIEWED` false until the corresponding controlled staging check. Keeping
   dispatch disabled still permits a separately reviewed ingress-only configuration for signed
   fixture testing. `VOICE_PROVIDER=disabled` remains the default. Even selecting `vaani` in
   the customer API continues to return unavailable in this phase. The current explicit
   voice-development Compose override enables only signed ingress for synthetic checks and
   blocks ordinary customer/admin routes while the tunnel is exposed.
5. From `backend`, run `venv\Scripts\python.exe -m tools.vaani_preflight`. It performs only
   read-only account/agent checks and prints sanitized status. A successful list response plus
   matching configured agent is required; the refreshed running container passed both checks.
   Use `--container --offline` to detect stale container configuration without provider requests.
6. Prepare a deliberate server-owned synthetic session: allowlisted internal Clerk UUID,
   test entitlement, current microphone/vendor-processing consents, no case data and a durable
   provider-room binding. The internal `bind_synthetic_call` seam is implemented, but **no
   public binding endpoint or complete real dispatch orchestration is enabled**. V2b must
   resolve call dispatch/BYOL connection ordering and uncertainty before a real smoke call.
7. Confirm agent no-fallback settings, signed lifecycle payloads, duration seconds, actual
   provider forced-end/cap and secret rotation. Then run one explicit fictional development
   call, collect sanitized evidence and check reconnect, revocation and termination. This
   call has not happened; mock/transport fixtures do not substitute for it.

An unauthenticated connection, unknown call ID, ordinary mock session, disabled identity,
missing/revoked consent, expired session or second concurrent socket is intentionally rejected.
Vaani's generic connection test may therefore fail until the server-owned call binding exists.
Do not weaken this boundary to make a dashboard indicator pass.

## Hosting readiness

[Back4app Containers documents WebSocket support and SSL-enabled domains](https://www.back4app.com/docs-containers/release-notes).
It is a plausible host for this FastAPI WSS/HTTPS service. The actual selected deployment,
domain, plan timeouts, idle behavior, outbound provider access, worker availability and TLS
routes have **not** been verified. This refers to Containers, not Parse LiveQuery. Vercel's
Next.js deployment remains the frontend; use a separately verified Python backend hostname
for BYOL and webhooks.

## What is still blocked

- Account credentials and owned development agent UUID now pass; these are no longer blockers.
- Stable staging host beyond the temporary Quick Tunnel, with matching private secrets.
- Saved no-fallback agent/retention settings and genuine signed webhook deliveries.
- Real dispatch-to-binding orchestration, uncertain-operation reconciliation/status polling,
  LiveKit browser audio and provider termination evidence. The adapter does not auto-retry
  a timed-out dispatch: a call might already exist.
- Qualified policy tools/calculator capabilities, privacy approval, real human review workflow,
  subscriptions and billing remain later gates. The current BYOL answer is a fixed AI-disclosed
  unavailable response, with no factual insurance advice.

Sources: [agent creation and ID](https://docs.vaani.dev/getting-started/create-agent),
[BYOL protocol](https://docs.vaani.dev/guides/byol),
[webhook signatures](https://docs.vaani.dev/guides/webhook-setup),
[WebRTC dispatch](https://docs.vaani.dev/api-reference/trigger-call).


## Dashboard connection error

A saved URL/token does not enable BYOL. Current BYOL and review flags are false and the
actual database has zero provider-call bindings. A generic dashboard test is therefore
expected to be rejected even with the correct token; fresh local/public ingress passed
12/12 checks each. Controlled server-owned session binding and provider termination are
still engineering prerequisites. Do not rotate credentials or bypass consent/ownership checks
to make Start Test pass. See the latest connection-error section in the Docker/tunnel report.
