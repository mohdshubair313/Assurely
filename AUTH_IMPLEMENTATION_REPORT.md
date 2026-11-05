# Clerk authentication implementation report

2026-11-04 — PROMPT 1. **Official Python SDK and real development keys integrated;
local checks passed. Authenticated user-session acceptance and production rollout
remain pending.** No production
credentials, reviewer qualifications or insurer approvals were invented.

## Official Python SDK / live configuration follow-up

- Added `clerk-backend-api==7.1.0` using `uv add clerk-backend-api==7.1.0 --frozen`;
  pinned it in the existing production constraints. The `--frozen` add preserves
  the repository's existing pip/Docker constraints workflow without relocking or
  upgrading unrelated dependencies. No new lockfile/migration architecture was introduced.
- Clerk-mode FastAPI requests now call the official Python `authenticate_request()`
  with the already fetched issuer-pinned public PEM, explicit `session_token` type,
  authorized parties and audience configuration. SDK verification does not replace
  Assurely's required issuer/v2/time/session/ownership/role checks. Legacy OIDC stays
  separate. No schema or graph edge changed in this follow-up.
- Corrected the user-supplied typo names privately, configured Next's ignored local
  environment, and made read-only real provider checks. Public JWKS, secret-key
  acceptance at the fixed Clerk Backend API, and matching instance signing keys
  all passed. Only sanitized booleans are recorded in
  `artifacts/clerk-config-check-20261104.json`; no credentials are printed or committed.
- Live configured browser checks passed for sign-in and sign-up widgets, anonymous
  workspace redirect, BFF 401 and public landing. Receipt:
  `artifacts/clerk-live-ui-20261104.json`; screenshot:
  `artifacts/clerk-live-signin-20261104.png`. No user account was created and no
  authenticated user JWT was minted or borrowed for these checks.
- Resolved the reproduced local Next/Clerk self-rewrite hang by aligning the server
  bind and configured origin to `localhost`. Auth code/headers remain intact.
- Local development Postgres was at revision 003. Created and validated a pre-change
  dump inside the existing DB container at
  `/tmp/assurely-before-clerk-20261104.dump`, then applied existing additive migrations
  004–010. Counts stayed **97 users, 99 sessions, 2 consent records, 0 saved profiles**.
  No old user was linked automatically or historical issuer changed. The dump is
  local development recovery material, not an encrypted production backup claim.
- Local frontend is running at `http://localhost:3000`; Python API is running on
  loopback port 8000 with Postgres/Redis/Chroma. `/health` returns 200 and unauthenticated
  `/v1/me` returns 401. Real-user authenticated journey, model-provider configuration,
  qualified roles and production release gates are still not certified.

Follow-up checks: **877 backend unit tests**, **10 Postgres integration tests**,
targeted Ruff/mypy and `pip check`; see SDK-specific XML artifacts below. Initial
875-test result and missing-key statements in the original implementation sections
below are historical, superseded by this follow-up's key/UI evidence.

`artifacts/backend-clerk-sdk-unit-20261104.xml` and
`artifacts/backend-clerk-sdk-postgres-20261104.xml` capture the Python-SDK reruns.

## Completed

- Audited Next.js 16, generic OIDC routes/cookies, backend JWT dependencies,
  user/session/consent/memory/escalation/audit/trace models and migrations 001–009.
  Findings and migration risks: [audit](AUTH_INTEGRATION_AUDIT.md).
- Installed official `@clerk/nextjs` **7.9.24**. Added conditional ClerkProvider,
  `proxy.ts`, catch-all sign-in/up, profile/sign-out controls, account loading/error
  UI, fixed internal post-auth destinations and explicit dynamic private-page guards.
  Public landing/education remain accessible. Private client state resets on
  account change. Personal statement entry now opens the protected workspace.
- The server gateway obtains a fresh session token through the SDK per request,
  accepts only session-token authentication and forwards it to FastAPI. Caller
  bearer headers, role fields and posted ownership cannot replace server authority.
  Privacy routing calls independently verified `/v1/me`; JWT payload decoding was removed.
- FastAPI independently verifies RS256, cached/rotating JWKS, exact configured
  issuer, expiry/not-before/issued-at, exact authorized party, Clerk v2 session/user
  claims and non-pending status. Optional configured audience is verified when used.
  Missing/invalid credentials return 401, forbidden ownership/role returns 403,
  missing configuration/JWKS connection outage/identity storage failure returns 503.
- Migration **010_clerk_identity** adds unique Clerk subject/issuer → stable local
  UUID bindings, an account-disable flag, append-only auth events and versioned
  consent. Concurrent creation is transactional. Existing UUIDs/history remain
  intact. No email matching, provider-user merge or destructive schema rewrite.
- Added reusable `AuthenticatedPrincipal`. Customer/admin/qualified reviewer/human
  advisor and independent publisher authority remain server-controlled local UUID
  allowlists. No user-editable Clerk metadata grants authority. Designated test
  accounts cannot review/publish/approve. Production rejects Clerk development issuers.
- Human advisors can access only active assigned escalations in Clerk mode.
  A separate admin endpoint records authenticated assignments with a rationale;
  assignment does not release reports. Review and release re-check assignment;
  release excludes designated test advisors. Existing exact digest/time/rationale
  review records and source/guardrail/delivery checks are preserved.
- Consent remains separate from sign-in. Version `2026-11-04` is explicit for
  comparison processing, saved profiles and updates. Added `/me/consents` and
  current-choice UI. Old receipts retain `legacy-v0`. Processing checks run before
  graph work; saved-profile consent is rechecked under a receipt row lock before
  persistence, preventing stale graph state from recreating revoked profile memory.
- Updated configuration examples, schema readiness revision, Docker public build
  arguments, README/deployment/integration docs, route matrix, sequence diagram,
  operator setup and rollback guide. Only environment variable names were inspected;
  no secret values were displayed or edited.

## Validation and evidence

| Check | Actual result |
| --- | --- |
| Full backend unit suite, offline Linux Docker | **875 passed**; includes 39 Clerk-specific verification/role cases |
| Disposable Postgres integration | **10 passed**: migrations 001–010, old UUID/session/consent preservation, concurrent mapping, restart lookup, issuer isolation/disable, consent/revocation, assignment, audit immutability, guarded/empty downgrade and session/hold refresh |
| Frontend transport/contracts and mocked Clerk/Next boundaries | **18 passed** |
| Actual browser against built standalone frontend, keys absent | **9 negative-check groups passed**, no browser exceptions or Clerk provisioning requests |
| Production Next build / TypeScript | Passed; product routes are dynamic, public landing/education static |
| Frontend ESLint | Passed after correcting the CommonJS test-harness variable name |
| Ruff | Passed on changed auth/consent/release runtime, migration and tests |
| Targeted mypy | Passed on nine auth/storage/API/authorization modules |
| Runtime npm audit | **0 vulnerabilities** with `--omit=dev`; installation still reports 16 moderate development-tool advisories |
| Git whitespace check | Passed |

Commands used from repository root unless indicated:

```powershell
docker run --rm --network none -v D:/Projects/InsuranceAI/backend:/app:ro -v D:/Projects/InsuranceAI/artifacts:/artifacts insuranceai-api:durable-test python -m tests.run_offline tests/unit -q -p no:cacheprovider --junitxml=/artifacts/backend-clerk-unit-20261104.xml

# Requires the explicitly disposable assurely_clerk_auth_test database/network.
docker run --rm --network assurely-clerk-test-net -e AUTH_TEST_DATABASE_URL=postgresql+psycopg://auth_test:synthetic-disposable-password@assurely-clerk-test-db:5432/assurely_clerk_auth_test -v D:/Projects/InsuranceAI/backend:/app:ro -v D:/Projects/InsuranceAI/artifacts:/artifacts insuranceai-api:durable-test python -m tests.run_offline tests/integration/test_clerk_identity.py -q -p no:cacheprovider --junitxml=/artifacts/backend-clerk-postgres-20261104.xml

# In frontend:
npm run test:contracts
npm run build
npm run lint
npm audit --omit=dev --json

# With a local unconfigured frontend running:
node scripts/verify_clerk_unconfigured.cjs
```

The database password shown in the isolated test command is a disposable test-only
fixture, not a deployment credential. The suite refuses any other database name.
The test database was recreated between runs; no live database was accessed.
For the built standalone smoke, static/public assets were copied into the build
artifact and the server used an explicit synthetic HTTPS `APP_ORIGIN`; the browser
script's `AUTH_BROWSER_ORIGIN` matched it. No actual provider/API was contacted.

Artifacts:

- `artifacts/backend-clerk-unit-20261104.xml`
- `artifacts/backend-clerk-postgres-20261104.xml`
- `artifacts/clerk-browser-negative-20261104.json`
- `artifacts/clerk-setup-required-20261104.png`

These ignored local artifacts contain synthetic checks, not production approval.
Earlier partial runs found an existing delivery-hold test expecting the previous
internal output to disappear even though continuations preserve it for audit. The
assertion now verifies preservation plus withheld public delivery; runtime output
generation/routing was not changed for that test. Initial TypeScript route caches
were stale after moving auth pages; regeneration/build resolved them. An initial
standalone smoke without a production-valid APP_ORIGIN returned configuration 503;
the explicit synthetic HTTPS-origin rerun passed without weakening origin validation.

## Scope decisions and remaining limitations

- **Not a live login claim:** genuine Clerk dev keys were not available in the
  checked environment-file names; no CLI account was provisioned. Browser login,
  real signup, logout and expiry/refresh are covered only at mocked SDK/synthetic
  JWT boundaries so far. Live provider acceptance must still be executed.
- The default backend provider remains `legacy_oidc` for explicit migration
  compatibility; deployment templates select `clerk`. Set both rollout switches
  deliberately. There is no automatic dual-provider token acceptance. Old OIDC
  endpoints/cookies are ignored in Clerk mode.
- Existing-user/provider inventory is unknown. No production user was linked.
  Linking old UUIDs requires operator ownership evidence; old issuer-scoped
  report/checkpoint continuity needs a separately reviewed plan before migration.
  Data preservation does not mean new-issuer access to old reports is already solved.
- Privileged authority uses existing operator-managed configuration rather than
  introducing a role administration database/UI. Qualification verification and
  the human authorization/change roster remain operational requirements. No
  software test certifies a professional's license or approves real policy data.
- Offline JWT verification cannot revoke an already-issued provider token instantly;
  it expires according to the signed lifetime. Local identity disablement blocks
  subsequent requests. Provider refresh/revocation behavior needs live checks.
- Consent revocation blocks subsequent processing; an authorized turn already in
  flight is not automatically cancelled. Profile saving has the additional fresh
  consent check. Reports/traces/checkpoints/backups have separate retention rules.
- No voice, recording, transcript, vendor sharing, billing or subscription feature
  was built. An AI voice guide cannot replace qualified human review.
- No graph node/edge, policy schema, model prompt, calculator constant or source
  approval was added/changed. No real deployment, production migration or push occurred.

## Exact next production setup

1. Configure owned **Clerk development** keys/domain origins in private Next settings,
   and matching backend issuer/JWKS/authorized parties per the
   [operator guide](docs/clerk-authentication.md). Do not share secrets in chat.
2. Back up and inspect the intended deployment's account inventory. Apply migration
   010 and existing checkpoint setup to staging; resolve old-account/issuer continuity
   first if real users exist. Keep staging and production data/instances separate.
3. Exercise genuine signup/login/logout, refresh/expiry, second-account denial,
   consent/revocation, reload/restart and persistent delivery holds. The code is
   ready for this acceptance step; it is not yet evidenced against Clerk's service.
4. Provision real operator accounts, verify qualifications, authorize local UUIDs,
   test audited escalation assignment and independent review/release with approved
   staging evidence. Confirm the owned notification receiver separately.
5. Configure the production Clerk instance (not its development issuer), Vercel and
   proposed backend hosting secrets, rebuild with public Next variables, run existing
   infrastructure/source/calculator/advisor/retention release gates, then deploy.

Detailed environment names, migration precautions, sequence diagram and route
matrix are in [docs/clerk-authentication.md](docs/clerk-authentication.md).
