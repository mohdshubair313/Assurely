# Clerk authentication: architecture and operator setup

Implemented 2026-11-04 for PROMPT 1. See the
[audit](../AUTH_INTEGRATION_AUDIT.md) and [evidence/report](../AUTH_IMPLEMENTATION_REPORT.md).
Live provider login and production release are not certified by local tests.

**SDK/configuration follow-up:** FastAPI now uses official `clerk-backend-api==7.1.0`
`authenticate_request()` with an issuer-pinned cached JWKS public key. Session-only
mode is explicit; Assurely additionally requires the exact issuer and complete
v2/time claims because the SDK alone does not require all of them. Legacy OIDC
keeps its separate verifier. The provided development keys were checked against
the public JWKS and Clerk Backend API, and the public/private instance keys match.
Genuine sign-in/up widgets render; actual user login/refresh still requires a user
to sign in. No account or test approval was created.

Local setup accepts canonical `CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` and
`AUTH_JWKS_URL`. `scripts/configure_clerk_local.py` safely normalizes the originally
supplied typo names after provider checks and prepares ignored frontend configuration.
Run it with a Python environment containing `httpx` and `python-dotenv`; it never
prints key values and refuses conflicting frontend settings. JWT verification is
networkless inside the SDK after the bounded public-JWKS fetch; it does not transmit
the secret key on each advisory request.

For this local Next.js version, use `npm run dev -- --hostname localhost --port 3000`
and visit `http://localhost:3000`, matching `APP_ORIGIN`. Binding the server to
`127.0.0.1` while visiting configured `localhost` reproduced repeated SDK self
rewrites before page rendering; aligning the bind/origin resolved it. No SDK auth
headers or guard checks were stripped to work around the failure.

## Identity and request contract

```mermaid
sequenceDiagram
    participant U as Browser
    participant C as Clerk
    participant N as Next server gateway
    participant F as FastAPI
    participant P as Postgres
    U->>C: Sign in / sign up through official SDK
    C-->>U: Short-lived session, SDK-managed refresh
    U->>N: Same-origin private API request
    N->>N: Server auth accepts session_token only
    N->>F: Bearer session token + server gateway credential
    F->>F: RS256/JWKS, issuer, time, azp, v2/session checks
    F->>P: Resolve (clerk, issuer, immutable sub)
    P-->>F: Stable local user UUID, disabled flag
    F->>P: Check owner / explicit operator roles / current consent
    F-->>N: Authorized result or 401/403/503
    N-->>U: Bounded JSON; held report content stays withheld
```

No email address is copied into the identity table. Concurrent first use creates
one user/mapping transaction, protected by a transaction lock and unique constraints.
All existing consent, sessions, traces, memory and escalation references continue
to use `users.id`. `/v1/me` returns that verified UUID, provider and server roles;
it never returns a JWT, signing key, Clerk secret or full provider profile.
The privacy gateway obtains ownership from `/me`; it does not decode token payloads.

JWT policy is pinned to RS256 and the configured HTTPS issuer's
`/.well-known/jwks.json`. JWK sets cache for 300 seconds; an unknown signing key
causes refresh, and fetch has a five-second timeout. Clerk mode requires `sub`,
`sid`, `v=2`, `iss`, `iat`, `nbf`, `exp`, and exact allowlisted `azp`. Pending
sessions and non-user/non-session subjects fail closed. Standard session tokens
need no `aud`; if `AUTH_AUDIENCE` is set, it becomes required and is verified.
Application code never takes issuer/JWKS URLs or roles from token metadata.

The SDK handles refresh/sign-out. FastAPI performs offline JWT verification, so
provider revocation is bounded by already-issued token expiry; it does not claim
instant remote session revocation. A local identity's `disabled` flag is checked
on every backend request. Keep clocks synchronized. No application test-token
shortcut exists in production code.

## Route / authorization matrix

| Surface | Access and authority |
| --- | --- |
| `/`, `/how-it-works`, policy education | Public; personal statement entry opens private workspace |
| `/sign-in/…`, `/sign-up/…` | Official Clerk SDK; fixed internal post-auth destinations |
| `/workspace`, `/intake`, `/comparison`, `/handoff` | Dynamic server session check; client state resets on account change |
| `/advisor` | Signed-in view; every review operation separately requires human-advisor role and assignment |
| `/api/backend/*` | Fixed route whitelist, server session token, no caller token substitution; same-origin JSON writes |
| `/v1/me`, `/v1/me/consents` | Verified mapped user, self context only |
| `/v1/message` in Clerk mode | Authenticated owner and current `process_comparison` consent before graph work |
| `/v1/session/{id}`, report status/recovery/release | Existing same-owner/durable turn/report checks; refresh never releases a hold |
| `/v1/consent`, profile deletion | Verified owner, explicit purpose/version; caller UUID cannot authorize another account |
| `/v1/policy-reviews/*` | Operator-qualified policy reviewer UUID allowlist |
| `/v1/policy-publications/*` | Separate publisher authority; source review alone cannot publish |
| `/v1/advisor-reviews/*` | Authorized human advisor, independent from owner, active assigned escalation |
| `POST /v1/admin/escalations/{id}/assign` | Separate admin role; authorized provisioned advisor only; immutable audit event; no release |
| `/health`, `/ready` | Minimal service health; no personal data |
| Legacy `/api/auth/*` | Disabled in Clerk mode; explicit OIDC rollback only |

The backend gateway credential is an additional ingress boundary, never a user
identity or permission. Operator endpoints intentionally remain outside the general
customer BFF whitelist. No voice/audio/websocket or billing endpoint is introduced.
No tenant selector is accepted; ownership is bound to an individual local UUID.
Multi-tenant administration is future scope, not inferred from Clerk organization claims.

## Server role policy

Every new user is a customer. `users.role` and Clerk user-editable metadata do not
grant privileges. Operator-owned **local UUID** allowlists are authoritative:

- `ADMIN_SUBJECTS`: assignment/operational authority, without implicit source review.
- `POLICY_REVIEWER_SUBJECTS`: explicitly qualified source reviewers.
- `POLICY_PUBLISHER_SUBJECTS`: independent publication authority.
- `ADVISOR_SUBJECTS`: human advisor review, restricted to active assigned escalations.
- `AUTH_TEST_SUBJECTS`: local test-account UUIDs excluded from privileged roles and
  release-time advisor authority, even if mistakenly included in another list.

Provision each person through real sign-in first; obtain their UUID from `/me`.
The operator must verify professional suitability/qualifications and retain the
authorization/change record before adding privileged UUIDs. These lists are not
evidence that a person is licensed. No role-grant endpoint, first-user admin rule,
sample privileged UUID or automatic metadata sync is installed. Restart services
after changing configuration. Separate reviewer/publisher identities remain a
production preflight requirement. Clerk development instances cannot authenticate
against a production backend. Use separate instances/databases for test and production.

Existing review and advisor decision tables continue to bind authenticated actor,
time, exact evidence/report digest, revision and rationale. `auth_events` adds
append-only identity/consent/assignment events. Assignment and release re-check
the current advisor relationship; assignment alone never approves a report.

## Consent

Version `2026-11-04` has three separately grantable purposes:
`process_comparison`, `save_profile`, `receive_updates`. `/me/consents` supplies the
published purposes and actual current grants. A grant must explicitly name the
current `purpose_version`; revocation does not require accepting a new version.
The intake checkbox and privacy controls send the displayed version. Old receipts
remain `legacy-v0` and do not authorize Clerk processing or saved-profile reuse.
Renewing an old version revokes its active receipt and creates a new one.

Login grants none of these permissions. Processing consent is checked before
each message; withdrawal blocks subsequent processing, rather than cancelling
an already-authorized turn in flight. Saving is checked again under a receipt row
lock at persistence so stale graph consent cannot recreate revoked profile memory.
Withdrawal deletes saved memory. Operational case/traces/checkpoints and backups
have separate retention obligations; this is not a full record-erasure implementation.
Updates consent does not create a messaging channel. Audio recording, transcript
retention, voice-vendor sharing and marketing expansions are not authorized by
these purposes; their services are not built in this change.

## Development setup

1. Use an owned Clerk development application in the dashboard. No CLI provisioning
   or existing account/password migration has been run by this implementation.
2. Configure the Next environment (see `frontend/.env.example`):
   `NEXT_PUBLIC_AUTH_PROVIDER=clerk`, `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`,
   server-only `CLERK_SECRET_KEY`, exact `APP_ORIGIN`, `BACKEND_URL`, and
   server-only `BACKEND_GATEWAY_TOKEN`. Configure `/sign-in` and `/sign-up` paths.
   Never put a secret key or gateway credential under `NEXT_PUBLIC_`.
3. Configure FastAPI: `AUTH_PROVIDER=clerk`, exact dashboard `AUTH_ISSUER`,
   matching `AUTH_JWKS_URL`, and JSON `AUTH_AUTHORIZED_PARTIES` containing the exact
   frontend origins. Do not use `*`, trailing path/slash variants or arbitrary
   preview origins. Leave `AUTH_AUDIENCE` empty for standard Clerk session tokens.
4. Back up the database; run `alembic upgrade head` in the backend migration job.
   Confirm revision `010_clerk_identity`. Run existing checkpoint setup separately
   for staging/production; migration 010 does not replace checkpoint migrations.
5. Start services, sign up/sign in, check `/api/backend/me`, grant only the needed
   processing purpose, submit intake, reload the case and confirm holds remain.
   Exercise logout, session expiry/refresh, a second account, revoked consent,
   authorized assignment and independent review before claiming live E2E success.

Without genuine Clerk keys the public site and educational pages render, while
account UI states configuration is pending and private APIs fail closed. Keyless
Clerk provisioning is deliberately avoided. Real signup/login cannot be certified
from the synthetic-key and mocked SDK tests.

## Vercel / Back4App and production

Use `deploy/vercel.env.example` and `deploy/backend.env.example`. For the existing
frontend domain, set exact `APP_ORIGIN=https://assurely.shubair.in` and that origin
in the backend authorized parties and owned Clerk domain configuration. Backend
uses HTTPS, private Postgres/Redis, current migrations and existing preflight gates.
Clerk's issuer/JWKS configuration is copied from the actual production instance;
it must not be fabricated from a guessed domain.

Public Next variables are **build-time** values: configure them in Vercel before
building and redeploy after changes. Docker builds accept
`--build-arg NEXT_PUBLIC_AUTH_PROVIDER=clerk` and
`--build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=…` (publishable value only).
Inject `CLERK_SECRET_KEY`, `APP_ORIGIN`, backend URL and gateway secret at runtime;
never pass secret keys as Docker build arguments. Use separate staging/production
instances, databases and origins; do not authorize every preview automatically.

Run `python -m app.ops.preflight --help` for the existing readiness tool options.
Infrastructure checks do not approve actual insurer data, calculator assumptions,
advisor decisions, retention policy or live provider operation. Auth configuration
alone is not a launch approval.

## Existing users and rollback

The live account/database inventory is unknown; no live DB was accessed. Before
switching an existing deployment, identify its current provider and back it up.
Never merge users by email or rewrite user UUIDs. An operator-confirmed identity
link may insert the new Clerk binding to the evidenced existing UUID using a
parameterized, audited database migration. There is no browser linking API.
The unique local-user binding prevents silently attaching a second Clerk identity.

Historical reports/checkpoints also include their original issuer. Merely linking
a UUID does not make a new issuer a valid historical report namespace. Retain the
old issuer records and establish an explicitly reviewed continuity migration or
archive path before migrating real users. No bulk issuer rewrite is implemented.

For rollback, restore **both** `NEXT_PUBLIC_AUTH_PROVIDER=legacy_oidc` and
`AUTH_PROVIDER=legacy_oidc`, rebuild Next, restore the previous owned OIDC settings
and rotate its encrypted-cookie secret to require fresh old-provider login. Cookies/tokens
from one mode are never silently accepted as the other. Keep migration 010 and
all records: its downgrade refuses populated auth/events/current-version consent.
Rollback cannot erase audit history or resurrect revoked consent.

## Documentation references

- [Clerk Next.js setup](https://clerk.com/docs/nextjs/getting-started/quickstart)
- [Clerk middleware and resource authorization](https://clerk.com/docs/reference/nextjs/clerk-middleware)
- [Clerk session claims](https://clerk.com/docs/guides/sessions/session-tokens)
- [Manual session JWT verification](https://clerk.com/docs/guides/sessions/manual-jwt-verification)

Current SDK installed: `@clerk/nextjs` 7.9.24. Next.js uses `proxy.ts`; private
resource checks remain explicit rather than assuming the proxy protects routes.
