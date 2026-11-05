# Frontend API integration audit

Updated 2026-11-04. Scope: Phase 1 customer/advisor web journeys. This is code and
synthetic integration evidence, not approval to launch with real policy data.
Clerk is now integrated in code; genuine provider setup and live login verification
remain pending. Voice is separate future work and cannot replace human approval.
See [Clerk setup](clerk-authentication.md) and [implementation report](../AUTH_IMPLEMENTATION_REPORT.md).

## Connected customer and advisor endpoints

| Backend API | Frontend integration | Safety boundary |
| --- | --- | --- |
| `POST /v1/message` | Guided `/intake` and customer `/workspace` | Bounded nonblank question, UUID, closed validated scenario; held report content discarded |
| `GET /v1/session/{id}` | Workspace case-activity action | Same-owner backend read; client consumes metadata only, not hidden report side channels |
| `GET /v1/sessions/{id}/report-status` | Workspace, comparison and handoff | Validated turn/digest/status; metadata never grants delivery |
| `POST /v1/sessions/{id}/report-release` | Workspace and connected report views | Stable case/turn/digest request key, exact receipt binding, sourced nonempty report, fresh server checks |
| `POST /v1/sessions/{id}/recover-turn` | Workspace interrupted-turn action | Exact turn receipt; no automatic message replay |
| `POST /v1/advisor-reviews/sessions/{id}/snapshot` | Advisor current-case lookup | Authenticated advisor; snapshot comes from server state |
| `GET /v1/advisor-reviews/{digest}` | Advisor exact report/scenario | Validated report/scenario/revision; current authorized advisor only |
| `POST /v1/advisor-reviews/{digest}/decisions` | Advisor approve/revoke actions | Nonblank reason, integer revision, bounded future expiry, stable request key; approval never directly delivers |
| `POST /v1/consent` | Explicit intake processing receipt and workspace privacy controls | Browser supplies scope/action only; backend verifies JWT and matching owner |
| `DELETE /v1/profile-memory/{id}` | Explicit profile-deletion confirmation | Fixed logical gateway path; target shaped server-side; origin, JWT and matching-owner checks |

The browser uses same-origin `/api/backend` routes. Bearer and gateway credentials
stay server-side in the gateway. Clerk SDK manages browser sessions; the gateway
obtains a session token per request. Consent/deletion ownership comes from FastAPI's
independently verified `/v1/me`, never from decoding JWT payloads. Clerk subjects
map to stable local UUIDs. Client-supplied `user_id` is rejected by this gateway.
Clerk-mode messages require authentication and current processing consent; the
public landing statement form routes users to private onboarding before submission.

## What changed

- The guided intake now retains answers across steps, validates household fields,
  records explicit processing consent for the signed-in account and sends a real
  message. Preference ranges are labeled as user budget preferences, not premiums.
  Questions/health details are never placed in URL parameters or browser storage.
- The landing statement form also opens an actual case and exposes its case link.
  It does not treat submitting a statement as policy verification. Removed hardcoded
  policy/legal findings from the unused legacy claim-checker component's defaults;
  it now requires explicit findings and verification dates from its caller.
- `/comparison` now loads the actual case status and opens only a freshly released
  sourced report. The old placeholder matrix is no longer this route's output.
- `/handoff` shows real turn/report metadata. It does not invent escalation reasons,
  sharing guarantees, notification completion, advisor contact or a response time.
  There is no backend owner-facing advisor-notification status endpoint yet; report
  metadata cannot establish whether a notification reached its receiver.
- Workspace scenarios support up to five distinct policy references against one
  explicitly shared context. Exact numeric policy answers still come from the
  backend; missing/null context remains unknown. The backend accepts independently
  different contexts/capability sets, but this customer form intentionally exposes
  one shared scenario and one selected capability at a time.
- Client calls now have runtime decoders rather than unchecked generic casts.
  Every displayed report sentence must have citations, dates and safe HTTPS source
  references. Invalid successful responses cannot enable release or render claims.
- Cancellation and a synchronous action lock suppress old-case results and rapid
  duplicate clicks. Reads can be repeated explicitly; writes are not automatically
  retried. Release/recovery/decision retries reuse their exact bound keys. Message
  submission has no server idempotency key: after an ambiguous network failure,
  inspect the case before manually submitting again.
- Errors retain useful HTTP categories (sign-in, permission, missing case, conflict,
  validation, size, rate limit, unavailable). Private backend error bodies are never
  reflected. Numeric retry guidance is preserved; no retry loop is introduced.
  Writes including DELETE require same-origin JSON and bounded bodies. Success
  payloads must be bounded JSON objects; request cancellation propagates upstream.
- Product loading and error boundaries use the installed Next.js conventions.
  Failure UI shows no stack, tokens, health details or provider exception text.

## Privacy scope

Privacy controls load current versioned consent from `/v1/me/consents` and record
explicit grant/revoke receipts. Login grants no insurance consent. Old receipts are
retained as `legacy-v0`, not silently upgraded. Withdrawal of `save_profile` deletes stored
profile memory under the existing backend contract. Profile deletion does not
erase reports, immutable decisions, checkpoints or backups; their retention and
deletion lifecycle remains a separate launch gate. `receive_updates` records
permission only; it does not implement a notification/reminder channel. No
comprehensive statutory-consent or record-erasure compliance approval is claimed.

## Deliberately separate APIs

The eleven policy-review/publication APIs remain authenticated operator tooling:
draft staging/read/review/import-check; publication comparison/requirements/proposal/
read/decision/term-import/lookup. They are **not** customer-facing gateway routes.
Uploading raw policy PDFs or publishing insurer facts needs a separate operator
interface and genuine qualified review, not a generic customer proxy. Existing
operator APIs/tools remain available; no artificial customer API, policy catalog,
premium quote endpoint or source approval was invented to fill a screen.

`/v1/webhook/whatsapp` is deferred channel scope; `/health` and `/ready` are operational
probes. Existing account routes are unchanged. Thus the ten customer/advisor APIs
are connected; this work does not claim a web administration console for every
backend endpoint, a Clerk rollout, voice calling or real-source qualification.

## Verification and local reproduction

The new runtime-contract suite uses Node's built-in test runner. From `frontend`:

```sh
npx tsc lib/api-contracts.ts lib/api-client.ts lib/intake.ts --outDir ../artifacts/integration-client --module commonjs --target ES2022 --skipLibCheck --esModuleInterop
node --test tests/api-contracts.test.cjs
```

The positive browser paths use the dedicated fixture described in
[release gates](release-gates.md), including its synthetic gateway key. Run:

```sh
node scripts/verify_advisory_journey.cjs
# Set ASSURELY_SYNTHETIC_BROWSER_TEST=1 in this process only.
node scripts/verify_frontend_integration.cjs
```

The latter explicitly labels mocked negative/race cases; positive consent, session,
review, release and intake requests use the real Next/BFF/FastAPI/Postgres boundaries.
Only the fixture's model-backed intake/intent/retrieval nodes are synthetic. It does
not establish real model extraction quality or genuine source/identity approvals.
The proposed Vercel/Back4App deployment still needs its actual environments,
identity registration, qualified evidence and live journey verification; see
[deployment instructions](production-deployment.md).
