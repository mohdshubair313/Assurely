# Release gates and operator handoff

Updated 2026-11-04. This is an evidence inventory, not a production release approval.

Deployment packaging and the owner's Vercel/Back4App plan are documented in
[production deployment](production-deployment.md). The software templates do not
close genuine account/source/operations approvals.
Customer/advisor endpoint coverage and connected intake/comparison/handoff/privacy
flows are recorded in the [frontend integration audit](frontend-api-integration.md).

| Gate | Software/evidence available | Still needed for real users |
| --- | --- | --- |
| Policy facts | Source review, authenticated representation/publication/import, exact scoped comparisons and fresh checks | Qualified review of genuine policy/variant/condition evidence and missing complete tariffs; no synthetic approvals may be promoted |
| Calculators | Deterministic arithmetic; unverified assumptions identified; excluded from reviewed scoped reports | Qualified assumption evidence/sign-off before any calculator recommendation is delivered |
| Login | Clerk SDK, independent v2 RS256 verification, local UUID mapping, explicit operator roles and versioned consent; synthetic tests | Owned Clerk keys/domain configuration, role/qualification roster, existing-user continuity audit if applicable, genuine login/refresh E2E |
| Advisor | Exact-report staging, independent approval/revocation, expiry and transactional owner release; browser journey tested | Genuine authorized advisor accounts and approved notification destination/receiver verification |
| Durable execution | Postgres checkpoints, isolated turns, owner recovery; application and native migrations tested | Apply reviewed migrations to the intended deployment, configure access/encryption and connection capacity |
| Recovery operations | Synthetic dump/restore, actual Postgres restart and protected checkpoint read passed | Production backup storage/encryption, restore drill, infrastructure failover and documented retention/deletion policy |
| Frontend | Real customer/advisor workspaces and same-origin backend gateway; desktop/dark mobile checked | Live provider/source journey with genuine identities and approved evidence |
| Dependencies | Next.js 16.4.4, openid-client 6.8.9; runtime dependency audit has zero advisories | 16 moderate development lint-tooling advisories remain; do not force an incompatible tool downgrade |

The local test graph replaces only model-backed intake/intent/clause retrieval
with synthetic nodes. Actual comparison, reviewed guardrail, report, escalation,
decision trace, Postgres checkpoint, JWT verification, advisor and release paths
run normally. Notification remains unconfigured in that fixture. The local HTTPS
OIDC fixture checks PKCE and returns signed identity tokens; it does not certify
a real identity provider or grant genuine policy approval.

## What the owner needs to decide

Clerk is confirmed for real user accounts. The owner still needs to appoint people
qualified to review insurance evidence and customer reports. Those people must
actually review the relevant material. Account passwords, API secrets and private
keys belong in deployment secret storage, never an issue, PR, screenshot or chat.

## Account and frontend setup: current Clerk path

Follow [Clerk authentication](clerk-authentication.md) for migration 010, Vercel
environment names, local UUID mapping, consent and live acceptance checks. Do not
configure the old OIDC callback for Clerk. No genuine provider login has been
verified by the synthetic tests. Voice cannot replace independent human approval.

## Legacy OIDC rollback setup only

The steps and cookie behavior below apply **only** when both frontend and backend
are explicitly switched to `legacy_oidc`. They do not describe the Clerk session.

1. Copy `frontend/.env.example` to a private local/deployment environment file.
2. Set `APP_ORIGIN` to the exact public HTTPS origin and `BACKEND_URL` to the trusted
   backend origin. Configure the reverse proxy to preserve the public callback origin.
3. Generate a unique random 32-byte base64 `SESSION_SECRET` in a secret manager;
   use the same value on frontend replicas. The synthetic fixture's secret is not
   a deployment value. Rotation invalidates existing browser sessions.
4. Register a confidential or public OIDC client as appropriate. The exact callback
   is `${APP_ORIGIN}/api/auth/callback`. Set `OIDC_ISSUER`, `OIDC_CLIENT_ID` and, when
   required, `OIDC_CLIENT_SECRET`. `OIDC_SCOPE` defaults to `openid`; add the provider's
   API scopes. `OIDC_RESOURCE`/`OIDC_AUDIENCE` are optional provider-specific parameters.
5. Ensure access tokens are RS256 JWTs for the backend's configured issuer/audience,
   with UUID subjects. Configure `AUTH_ISSUER`, `AUTH_AUDIENCE`, `AUTH_JWKS_URL` and
   explicit reviewer/publisher/advisor UUID allowlists on the backend. Client claims
   or UI controls never confer those roles.

Sign-in runs on the identity provider. The frontend stores the access token only
in an authenticated-encrypted HttpOnly, SameSite=Lax cookie; production cookies
are Secure. No bearer credential is returned by the account-status endpoint or
stored in browser JavaScript/localStorage. Sessions last at most 15 minutes and
never outlive the advertised token lifetime. Larger-than-cookie tokens fail closed.
There is no refresh-token persistence: expiry requires sign-in again. Sign-out
clears this application's cookies; provider-wide sign-out/revocation is separate.

The `/api/backend` gateway has an explicit path/method allowlist, validates write
origins/content type, applies request/response size limits and never forwards
client-selected bearer headers or arbitrary backend URLs. Backend authorization
and delivery gates still run for every request. Set `CORS_ORIGINS=[]` for a backend
used only through this server gateway, or list exact trusted HTTPS browser origins;
the API no longer enables wildcard credentialed CORS.
Apply deployment-level rate and request-budget limits to account sign-in and
public message ingress as well as the backend's existing model-call controls.

## Deployment verification

After a backup and migration review, rebuild dependencies and run against the
intended database:

```sh
alembic upgrade head
python -m app.db.setup_checkpoints
python -m app.ops.preflight --database
```

The preflight emits only boolean gate states and required external evidence. It
does not print credentials, mutate approval data or authorize release. A passing
configuration report is not source qualification, legal approval or a live delivery
test. Missing migrations/configuration remain visible failures.

The root Compose file is a development configuration with local credentials
and `ENVIRONMENT=development`. Its backend now explicitly builds
`Dockerfile.development`; the default backend Dockerfile builds the production
image. The separate `deploy/compose.production.yml` is an optional portable host
template, initially bound to localhost. The owner's existing frontend remains
on Vercel; see the deployment guide for proposed Back4App Containers settings. Use a
managed secret store, restricted database roles, encrypted transport/storage and
TLS termination; avoid publishing database/Redis/Chroma ports on public interfaces.
Budget connections for a dedicated execution-lock connection per active turn plus
node work and the independent checkpoint pool. Choose retention for conversation,
health state, immutable approvals and backups before enabling real-user collection;
this change does not invent a deletion period or automatically purge audit data.

## Reproducing the browser evidence

Only use disposable databases and synthetic credentials. `tests.browser_server`
refuses to start without `ASSURELY_SYNTHETIC_BROWSER_TEST=1` and the exact dedicated
`policy_review_test_terms` database. It uses the installed backend test image and
exports temporary fixture certificates/tokens under ignored `artifacts/`.

1. Start a disposable Postgres container named `insurance-gates-db`, and the fixture
   API named `insurance-gates-api`, on a dedicated Docker bridge. Publish only the API
   to host loopback port 18000. Mount the backend read-only and artifacts writable.
2. Start `scripts/synthetic_oidc.cjs` with the explicit synthetic flag. It serves
   only the local HTTPS fixture on port 19443. Its disposable CA is trusted only by
   the test frontend process using `NODE_EXTRA_CA_CERTS`.
3. Start Next development on port 3000 with `BACKEND_URL=http://127.0.0.1:18000`,
   `OIDC_ISSUER=https://localhost:19443`, `OIDC_CLIENT_ID=synthetic-browser`,
   `APP_ORIGIN=http://localhost:3000` and the fixture-only base64 key corresponding
   to 32 bytes of value 7. Set the frontend's `BACKEND_GATEWAY_TOKEN` to
   `synthetic-browser-gateway-key-only-20261103` to match the isolated test server.
   Do not use these values outside this synthetic test.
4. Run `node scripts/verify_advisory_journey.cjs` using the repository's local
   Playwright installation (`npm install --prefix .local/browser playwright`) and
   installed Edge. Then, with the explicit synthetic flag, run
   `node scripts/verify_database_recovery.cjs`. The latter creates only the dedicated
   restore database, copies a synthetic dump and restarts the named test Postgres.
5. Stop/remove the fixture containers, provider and test frontend; remove transient
   certificates, keys, tokens and synthetic dump after retaining redacted result
   JSON and screenshots. No application database is touched by these tests.

Evidence lives in ignored artifacts: browser result JSON, four actual screenshots,
database recovery result JSON, migration smoke output and preflight test receipt.

## Source follow-up

The official [Care product page](https://www.careinsurance.com/product/care-supreme)
and [premium-revision rationale](https://selfcare.careinsurance.com/data/Care%20Supreme%20-%20Rationale%20for%20Premium%20change.pdf)
were located again on 2026-11-03. These sources do not establish the complete
applicable tariff matrix needed by this implementation. No inference of a full
rate chart, missing exclusion rule or calculator calibration was promoted. Existing
Care/HDFC/Star candidate packages retain their pending qualification status.
