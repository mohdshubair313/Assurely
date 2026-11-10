# Reviewed case binding and source-linked text companion

**Later checkpoint on the same date:** the companion described here still does
not send report text. A separate default-off BYOL report-reading bridge now exists
and requires its own explicit report-export permission plus fresh release checks.
See [that implementation and its boundaries](VOICE_BYOL_EVIDENCE_IMPLEMENTATION.md).
The test results below describe this earlier binding checkpoint.

Checkpoint: 2026-11-09. This continues the approved voice implementation before
further provider credential work. Backend, frontend and regression code are
implemented locally. Customer calls and paid billing remain disabled.

## Functional contract

An authorized staging tester can select an owned, independently reviewed case for
an existing synthetic development voice session. The server selects the current
turn, report digest and actual authorized human decision; the browser cannot
submit report text, an approval, reviewer identity or a release receipt.

One immutable report version is bound per voice session. If the case turn,
report or advisor decision changes, the old binding fails closed. A new voice
session is required; a new request key cannot silently replace the binding.
The UI explains this limitation and keeps the existing workspace available.

The companion displays complete original report sentences with source links,
physical PDF pages, applicable conditions and last-verified dates. It is clearly
labeled reviewed report text, **not a live transcript**. No case content is sent
to Vaani by this feature, and no report sentence is passed to TTS. Synthetic BYOL
retains its existing fixed safe responses.

## Technical contract

| API | Effect |
| --- | --- |
| `POST /v1/voice/development/sessions/{voice_id}/case-binding` | Closed body `{case_id, idempotency_key}`; persist one immutable binding after current release checks |
| `GET /v1/voice/development/sessions/{voice_id}/case-binding` | Recover metadata after fresh lifecycle, consent and exact report-release checks |
| `GET /v1/voice/development/sessions/{voice_id}/captions` | Repeat those checks and return an ordered, source-linked `authorized_report_excerpt` |

Every endpoint requires verified Clerk ownership. Creation and reads require
`VOICE_CASE_BINDING_ENABLED=true`, evidence tools enabled, staging, an explicit
test-customer allowlist, current voice development readiness, an open connected
server-owned synthetic session and current identity/insurance/microphone/vendor
consents. Missing configuration or candidate schema fails closed. Default
configuration leaves the feature disabled.

Additive migration `016_voice_case_binding`, flagged before implementation, adds
immutable bindings with owner, issuer, voice/case identifiers, exact turn/report,
normalized request digest and original report-release receipt/advisor event.
Database constraints validate cross-table scope and reject edits/deletion.
Populated downgrade refuses to discard history. Migration files 011–015 are
unchanged. Earlier schemas remain compatible only with their newer features off.
No application database migration or application-service activation was performed.

Lock order is entitlement, voice session, provider binding/managed operation,
current identity/processing-consent share locks, binding request key, release
request key, report head, advisor report and existing publication controls.
Requests use one transaction. Network/provider calls do not occur in that
transaction or anywhere in this feature. Processing consent withdrawal serializes
against its locked receipt; voice withdrawal also uses the existing entitlement
lock. The same request key and normalized payload replay the original binding;
conflicting keys/cases/voice sessions cannot change it.

The implementation calls the existing `report_release.release()` authority on
every bind, metadata read and text read. It preserves current guardrail, exact
turn/report, independent assigned advisor, expiry, source applicability,
publication and newer human-request checks. The original release key and advisor
event remain fixed; a historical receipt never becomes permanent permission.
Graph output and its stored `reviewed_report_held` status remain unchanged.

Caption projection runs only after successful transactional release. It copies
full sentences and allowlisted citation/reference fields, preserving conditions
and source hashes. URL validation rejects non-HTTPS links, embedded credentials,
invalid ports, whitespace/control characters and backslashes. The browser
independently validates binding, sentence order, dates, sources and safe response
flags before display. It does not use `innerHTML` or fetch arbitrary source URLs.

The returned presentation expiry is at most ten seconds and never later than
session, advisor or source expiry. The browser rechecks about every four seconds,
clears text before reauthorization and after failures, and discards late responses.
It also clears text on blur, hidden/offline/page-exit states, parent authorization
loss and unmount. Returning requires fresh authorization. Already received text
is **not instantly revoked by server push**; this is a short display lease and
transaction-time decision, not a guarantee about later network delivery.

Only opaque account/case/session references and an idempotency key are kept in
session storage to recover uncertain binding writes. Report text, bearer tokens,
provider secrets and source packets are not stored there. Storage failures stop
the write. No new trace or report content is exported to observability services;
existing instrumentation and its dependency pins remain unchanged. The
[Langfuse masking guidance](https://langfuse.com/docs/observability/features/masking)
was consulted for this privacy boundary.

## Files changed

- Backend: `app/voice/case_binding.py`, `app/models/db/voice_case_binding.py`,
  migration `016_voice_case_binding.py`, voice development routes, core settings,
  schema compatibility and model registration.
- Frontend: `VoiceCaseCompanion.tsx`, `VoiceDevelopment.tsx`, same-origin BFF,
  `lib/voice/case-contracts.ts`, `case-api.ts`, `binding-attempt.ts`,
  `caption-display.ts` and `caption-lifecycle.ts`.
- Validation/configuration: new backend unit/PostgreSQL tests, frontend case and
  gateway tests, test compile commands and safe backend/deploy environment examples.
- Documentation: paired voice specs, root voice report, phase checkpoint and progress.

## Verification

- **1,046 full offline backend unit tests passed**, with network disabled and the
  dotenv-blocking test launcher. The 26 new focused unit cases overlap this total.
- **52 real PostgreSQL tests passed**, zero failures/errors/skips: 26 new binding
  cases, six report-release, five advisor-review and 15 human-review regressions.
  Tests used a dedicated disposable database, independent concurrent transactions,
  actual process recovery, immutable receipt/ownership enforcement, missing and
  revoked consents, expired approval, publication withdrawal, new case turns,
  customer review requests, idempotency conflicts and serialized race scenarios.
- **56 frontend contract/mock checks passed:** 28 API/Clerk gateway contracts,
  14 development/case-display checks and 14 media-controller mocks. The host-event
  regression covers blur, offline-to-online while unfocused, focus recovery,
  visibility and listener cleanup. These are not genuine provider/browser-device
  acceptance tests.
- Production Next.js build and its TypeScript checks passed. Changed-file ESLint,
  Python Ruff, targeted strict mypy and repository whitespace checks passed.
- Candidate migrations were exercised in disposable PostgreSQL tests only. No
  application migration, application-service restart, deployment, commit or push
  was performed. Owned test database/network resources were removed afterward.

Backend receipts: `artifacts/voice-case-binding-full-unit-20261109.xml` and
`artifacts/voice-case-binding-postgres-20261109.xml`. Final counts and boundaries:
`artifacts/voice-case-binding-results-20261109.json`.

The first expanded regression run exposed a test-only dependency-order failure:
migration 016 references the 008 release receipt table. The old release-migration
fixture now reverses empty 016 before its 009/008 round trip and restores it
afterward. The populated-history refusal remains unchanged; no foreign key or
applied migration was weakened. Bug-hunt guidance was used for that diagnosis.

## Implementation and acceptance boundaries

| Scope | Status |
| --- | --- |
| Immutable owned case/report binding and recovery | IMPLEMENTED; real PostgreSQL tests |
| Fresh consent, source and independent human-release checks | IMPLEMENTED; unit/PostgreSQL tests |
| Complete source-linked report companion and display lifecycle | IMPLEMENTED; frontend contracts and simulated event tests |
| FR11 / AC09 visible-source branch | IMPLEMENTED / TESTED for exact reviewed report text; natural speech/follow-ups not completed by this item |
| FR16 / AC02 / AC04 / AC12 binding/read branch | IMPLEMENTED / TESTED; no cross-owner or held text returned |
| FR08 live captions and interruption alignment | NOT IMPLEMENTED here; companion is not a live transcript |
| Actual Vaani audio/BYOL/TTS, device/language and human operations | UNVERIFIED / gated; no new provider probe or real call |
| Customer rollout, production billing and privacy/vendor approval | DISABLED / still pending |

Review found and fixed malformed URL acceptance in backend projection and a
frontend lifecycle gap where an online event could redisplay text while the
window remained blurred. A simulated blur/offline/online/focus regression now
requires fresh authorization before redisplay. Existing migration regressions
needed descendant reversal before testing older tables; production foreign keys
and populated-history safeguards remain intact.

## Remaining work

This does not close all V2–V5 criteria. Next build the separately gated provider
evidence bridge with buffered, complete-answer authorization and interruption
contracts. Retain fixed safe BYOL responses until that path is verified. Then
perform a deliberately configured fictional live-provider call, signed callback,
termination/reconnect and usage acceptance when credential work resumes.

Live transcript alignment, conversation summaries, broader approved calculator
scenarios, commercial cancellation/refund terms, vendor retention/deletion,
qualified human operations, accessibility and actual mobile/language acceptance
remain separate. No credentials are needed from the owner for this local checkpoint.
