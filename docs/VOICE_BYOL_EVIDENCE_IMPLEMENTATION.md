# Guarded BYOL reviewed-report bridge

Checkpoint: 2026-11-09. IMPLEMENTED locally behind
`VOICE_BYOL_EVIDENCE_ENABLED=false`. This is a restricted report-reading adapter,
not unrestricted conversation or verified Vaani speech. Customer calls and paid
billing remain disabled. Application services and databases were not migrated or
restarted for this checkpoint.

## Functional contract

Only the last user message can request an answer. The accepted English commands,
after case/whitespace/trailing sentence-punctuation normalization, are:

- `Read my reviewed report`
- `Read the reviewed report`
- `Read my report`
- `Please read my reviewed report`

The session must already have an immutable owned report binding from migration
016. The provider cannot choose a case, supply a report, approve a recommendation
or change the bound report. Other questions receive the existing fixed safe
operational response. There is no LLM, new retrieval store, new calculator,
graph node, graph routing change or alternative report writer in this bridge.

Before sharing report text, a separate current `voice_report_speech` permission
is required. Its dedicated purpose version is `voice-report-speech-2026-11-09`.
Microphone, vendor-audio, transcription and saved-summary permissions do not
grant this purpose. The UI and canonical purpose disclose that it is account-level
permission for future development sessions and their independently reviewed,
bound reports until withdrawal. Use fictional staging data only. Older general
and voice-purpose versions remain unchanged; older eight-purpose backend responses
are accepted without inventing a report-sharing grant.

A permitted answer contains the AI disclosure, complete original report sentences
including conditions, and their source references and last-verified dates. The
entire answer is buffered and checked before any response frame is sent. An answer
over 12,000 characters, unavailable binding or held report produces the safe fixed
response without partial report text. An authorization failure after factual
preparation withholds that factual frame.

The browser has separate load/allow/withdraw controls. Withdrawal is available
even before a successful permission-status read, unless the backend is known not
to support the purpose. Withdrawal during a locally active call also requests
durable call termination. It does not assert confirmed termination or settle usage.
Account changes/unmount abort stale UI work. Already exported text/audio cannot
be recalled by withdrawing permission.

## Technical flow and durable authority

1. Existing BYOL Bearer authentication, reviewed agent configuration, call-ID
   ownership, synthetic managed-session checks and exclusive connection lease
   precede the new handler. Provider system messages and `req_body` are untrusted.
2. `begin()` serializes under the existing entitlement-first lock order. A normalized
   operation digest and unique `(session_id, response_id)` receipt prevent duplicate
   sends. A retry never replays an earlier response, including after a process restart.
   Conflicting reuse is rejected; delayed older IDs cannot start new work.
3. `prepare()` rechecks identity, current processing/voice consent, separate export
   permission and the existing transactional report-release authority. This includes
   sources, expiry, new turns, newer review requests and actual human decision.
   Frozen binding/report/source identity is preserved.
4. `authorize_send()` performs those checks again, compares the complete content
   and evidence digests, and commits `send_unknown` before network I/O. Its permission
   deadline is at most two seconds and cannot exceed the earlier evidence/lease
   expiry. Runtime rejects an expired authorization and bounds socket send to one second.
5. A successful socket send can record `sent`. This records only that the ASGI send
   returned; it is not evidence of TTS playback, human receipt, provider termination
   or usage settlement. A crash/timeout remains non-replayable `send_unknown`.

Lock order: entitlement -> session -> provider call/managed operation -> identity
and consent -> response receipt -> existing release-request/report/advisor/source
controls. Provider I/O runs after commit, outside these locks. Revocation shares the
existing entitlement serialization. This is a bounded authorization window, not
instant recall or a guarantee against every post-commit change.

Candidate migration `017_voice_byol_turns` adds an owner/binding-constrained durable
receipt table and immutable transition triggers. It stores identifiers, normalized
operation/content/evidence digests and timestamps, not raw transcript or report text.
Transitions are pending -> prepared -> send_unknown -> sent; pending/prepared may
be interrupted or failed. Unknown sends cannot be relabeled unsent. Populated
downgrade refuses history deletion. Migrations 011-016 are unchanged. No application
migration was applied. Runtime accepts older schemas only with their newer features
disabled.

## Protocol, interruption and limits

The documented request/response shape is retained: config/greeting handshake,
`response_required`, matching call/response IDs, complete `response` frame and
`ping_pong`. No undocumented interruption command is introduced. A newer response
ID synchronously fences and cancels obsolete local work **before** awaiting renewal
or database access. Generation is checked at every awaited preparation/send stage.
The independent receive task observes new work while an answer is being prepared.

Already-sent TTS cannot be canceled by this local fence. Real audible interruption
latency, provider buffering, actual reconnect and termination remain unverified.
The publicly documented optional `end_call` field is not used as termination proof.

Frames are bounded to 32,768 UTF-8 bytes; duplicate JSON members and non-finite
numbers are rejected. Limits are 120 incoming frames and 30 new turns per minute
per connection, plus 128 durable response receipts per session. The local 32-ID
fingerprint window catches recent conflicting duplicates; older delayed wire IDs
are ignored rather than reprocessed. Reconnects retain the durable session budget
and receipt identity. Database stages time out after three seconds; cancellation
has a bounded wait. Socket closure releases its own connection lease only, never
voice reservations or financial ledger entries.

With the feature flag false, the previous fixed-response BYOL loop remains in use.
The legacy path was regression-tested against PostgreSQL after migration 017.

## Requirements and acceptance boundaries

| Requirement / criterion | Implemented and locally tested slice | Still open |
|---|---|---|
| FR01 / AC02 | Existing authenticated owner/call binding; cross-owner rejection | Real Clerk/Vaani/browser journey |
| FR02 / AC03 | Disclosure in the fully buffered response | Audible disclosure before genuine guidance |
| FR03-FR04 / AC04 | Separate versioned export grant; missing/stale/revoked consent blocks report export; fresh send check | Actual provider termination/deletion and end-to-end revocation |
| FR08 / AC06 | Newer-ID cancellation of unsent local work | Audible interruption, natural follow-ups and repeated/slower speech |
| FR11, FR16 / AC09, AC12 | Complete exact-report sentences, conditions, dated sources and fresh human-release checks | Broader conversation, language/audio quality and real spoken/caption alignment |
| FR10, FR22 / AC08, AC18 | Durable non-replayable response intents; no disconnect-induced settlement | Provider reconnect, termination and real usage/billing evidence |
| FR25 / AC21 | Bounded failure, no provider/system instruction authority or unsafe fallback | Live provider fault/latency acceptance |

These are scoped software acceptance results, not closure of the full original
criteria. FR12-FR15 general explanations/calculations/sales checks, FR23 conversation
recaps and all commercial/provider/privacy/actual-device gates remain as previously
documented. No new qualified reviewer or factual approval was fabricated.

## Verification evidence

| Check | Actual result | Evidence |
|---|---|---|
| Full offline backend unit suite | 1,084 passed | `artifacts/byol-evidence-full-unit-20261109.xml` |
| Focused bridge/privacy unit suite | 38 passed, included in full suite | `artifacts/byol-evidence-unit-20261109.xml` |
| Five-module PostgreSQL regression baseline | 88 passed | `artifacts/byol-evidence-regression-postgres-20261109.xml` |
| Final privacy-aware PostgreSQL bridge suite | 39 passed | `artifacts/byol-evidence-final-postgres-20261109.xml` |
| Existing fixed-response BYOL PostgreSQL checks | 6 passed | `artifacts/byol-evidence-existing-byol-postgres-20261109.xml` |
| Frontend contracts / development-case / media mocks | 30 + 14 + 14 passed | `npm run test:contracts`, `npm run test:voice-development`, `npm run test:voice-media` |
| Final production frontend build / TypeScript | Passed | `npm run build` after final UI edits |
| Changed-file ESLint / Ruff / targeted strict mypy / whitespace | Passed | Focused checks; no global type-cleanliness claim |

The PostgreSQL receipts contain **97 unique test identities**, not 133 different
tests: the final 39 bridge cases replace 36 overlapping baseline cases and add
three dedicated export-consent cases. The other baseline 52 cases cover binding,
report release, advisor and human-review behavior. The six legacy BYOL cases are
separate. All listed XML receipts contain zero failures, errors or skips. Earlier
focused/additional receipts are intermediate evidence, not extra unique coverage.

Unit tests and frontend media/SDK tests use mocks.
PostgreSQL tests use real transactions and migrations in a separate disposable
database, with fictional identities, reports and provider calls. They do not
contact Vaani, acquire microphone access or prove genuine audio delivery.

The tests exercise concurrent IDs/duplicate starts, conflicting normalized keys,
restart/no-replay, newer-ID cancellation including a delayed-heartbeat race,
expired authorization, uncertain socket sends, owner/lease/consent loss, altered
reports/human decisions, new holds, withdrawn evidence, immutable scope/history,
safe oversized fallback and unchanged usage/reservations. Existing binding,
human-review, advisor and report-release tests remain in the regression run.

An obsolete empty-database migration fixture now reverses all descendants before
exercising migration 008 and restores them in order. Populated-downgrade rejection
and production foreign keys were not relaxed.

The security reviewer found and closed two issues: delayed renewal could previously
allow old unsent work through before cancellation, and a session-only consent
description did not match account-level persistence. The fence now precedes awaits;
the canonical purpose and UI now disclose the real scope. No remaining concrete
security finding was reported in those deltas.

Backend units ran through `python -m tests.run_offline tests/unit -q
-p no:cacheprovider` in the Python 3.11 Docker image, with network disabled,
read-only source and the dotenv-blocking launcher. PostgreSQL runs used that
launcher against an isolated Postgres 16 test service, never the app database.
The owned test service and network were removed after completion.

## Files changed for this checkpoint

- Backend bridge: `backend/app/voice/byol_evidence.py`,
  `backend/app/voice/byol_runtime.py`, `backend/app/voice/byol.py`,
  `backend/app/api/v1/vaani.py`.
- Persistence/configuration: `backend/alembic/versions/017_voice_byol_turns.py`,
  `backend/app/models/db/voice_byol_turn.py`, `backend/app/models/db/__init__.py`,
  `backend/app/db/schema.py`, `backend/app/core/config.py`,
  `backend/.env.example`, `deploy/backend.env.example`.
- Separate privacy purpose: `backend/app/core/consent.py`,
  `backend/app/api/v1/consent.py`, `backend/app/api/v1/identity.py`,
  `frontend/lib/api-contracts.ts`, `frontend/lib/api-client.ts`.
- Frontend: `frontend/components/product/ReportSpeechConsent.tsx`,
  `frontend/components/product/VoiceDevelopment.tsx`,
  `frontend/components/product/VoiceCaseCompanion.tsx`.
- Tests: `backend/tests/unit/test_byol_evidence_bridge.py`,
  `backend/tests/integration/test_byol_evidence_bridge.py`,
  `backend/tests/integration/test_report_release.py`,
  `frontend/tests/api-contracts.test.cjs`.
- Documentation: this report, paired voice specifications,
  `docs/VOICE_CASE_BINDING_IMPLEMENTATION.md`, `VOICE_IMPLEMENTATION_REPORT.md`
  and `PROGRESS.md`; private/local verification artifacts remain under `artifacts/`.

The working tree also contains earlier uncommitted work. This list attributes only
the files edited for this checkpoint, not every existing modification to this task.

## External contract and deliberate deviations

Official [Vaani BYOL guide](https://docs.vaani.dev/guides/byol) was fetched publicly
on 2026-11-09 without provider credentials; snapshot is
`artifacts/vaani-byol-contract-20261109.txt`. The vendor example suggests using its
system prompt. Assurely deliberately ignores that suggestion: external system
messages cannot override existing authorization, human review or evidence controls.
Only the supported wire contract is reused. No Langfuse project/evaluator or raw
voice/report export was introduced; existing SDK pins remain unchanged.

## Activation and next work

Not activated: migration 017, the evidence feature flag, customer live calls,
provider fallback or paid subscriptions. No app service, secret, agent configuration,
tunnel or provider account was changed, and no deployment/commit/push occurred.

When credential/configuration work resumes, controlled fictional staging acceptance
must verify the real authenticated provider handshake, no fallback, matching call
IDs, spoken references/disclosure, interruptions, hard termination, consent withdrawal
and signed-event usage reconciliation. Reconfirm the current tunnel/domain instead
of reusing a historical URL. Broader natural conversation, genuine conversation
recaps, reviewed calculators, commercial cancellation/refund terms and V5 human,
vendor-privacy, deletion, mobile, language and accessibility evidence remain open.
