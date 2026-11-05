# Authentication integration audit — 2026-11-04

Scope: PROMPT 1 only. Clerk is the confirmed provider. This audit describes the
repository before the Clerk changes; it does not certify a deployed system.

## Existing boundaries

- Next.js 16.4.4 / React 19 use generic `openid-client` PKCE login under
  `/api/auth/[action]`, an encrypted HttpOnly access-token cookie, and no refresh
  persistence. Sign-in/up are ordinary pages. Product layout has no server guard.
- `/api/backend/[...path]` is an origin-checked, size-bounded, fixed route gateway;
  it forwards a server-held token and gateway secret. Privacy routing decodes an
  unverified UUID subject; FastAPI independently verifies it. Clerk requires a
  verified local identity lookup instead of this UUID assumption.
- FastAPI verifies RS256/JWKS, issuer, expiry, mandatory audience and UUID subject.
  Clerk has string subjects and default session tokens need not have an audience.
  Authorized-party, session-token type and pending-session checks are missing.
- Consent/profile/session/release endpoints enforce subject/owner matching.
  `/message` permits anonymous use; comparison-processing consent is not enforced
  at that boundary. Saved profile consent is queried server-side. Consent records
  are durable, purpose-specific but unversioned; sign-in must never grant them.
- Reviewer, publisher and advisor UUID allowlists are server-controlled; JWT role
  metadata is ignored. Reviewer/publication and exact-report decisions already
  persist actor, digest, rationale and time. Advisor access currently lacks the
  assigned-escalation restriction described in the user model.
- Users use UUIDs. Sessions own user UUIDs; consent and profile memory reference
  those UUIDs. Escalations reference sessions/advisors; audit_log and decision_trace
  reference sessions. Report/checkpoint namespaces also include the trusted issuer.
- Alembic 001–009 preserve source reviews, publication and report/recovery records.
  Production graph checkpoints use Postgres; development MemorySaver is ephemeral.

## Evidence limits and migration risk

No live database or provider account was inspected. Whether production users or
another provider are actually active is **unknown**. No environment values were
read, no Clerk CLI application provisioned, and no live identities were linked.
Existing local changes from earlier sessions are retained.

## Proposed additive changes (flagged before implementation)

1. Migration 010: external identity mapping unique on provider/issuer/subject,
   preserving all existing UUIDs; versioned consent and auth audit records.
   Never auto-link by email or accept browser identity/role metadata as authority.
2. Explicit provider switch: Clerk path plus retained legacy OIDC rollback path.
   Fail closed if configuration is absent. Never silently accept both issuers.
3. Clerk session verification, reusable principal and operator-only UUID roles;
   separate admin authority and assigned-escalation advisor checks.
4. Official Next SDK/provider/proxy and resource-level guards; verified `/me`
   gateway routing; current consent receipts and explicit purpose/version acceptance.
5. No graph nodes/edges, insurance source approvals or delivery rules are changed.

Existing-account migration requires an operator-confirmed identity inventory and
explicit linkage transaction with ownership evidence. Preserve old issuer-scoped
reports/checkpoints; do not bulk rewrite audit provenance. Roll back the provider
configuration to restore old-provider access while resolving issuer namespace
continuity. Migration downgrade must refuse to erase populated auth records.
