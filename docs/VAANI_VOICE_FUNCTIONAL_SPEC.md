# Functional spec: Assurely AI Voice Insurance Guide

**2026-11-09 guarded speech checkpoint:** a separately default-off report-reading
bridge now buffers complete original report sentences with dated sources and checks
current independent human release again before sending. Only explicit report-read
commands are supported; no unrestricted follow-up conversation is claimed. Sharing
requires the separate `voice_report_speech` purpose, version
`voice-report-speech-2026-11-09`, disclosed as account-level permission for future
development sessions until withdrawal. Audio/microphone consent does not grant it.
Newer response IDs cancel unsent local work; actual TTS cancellation is unverified.
This extends the exact-report software branch of FR11/FR16 and AC04/AC09/AC12,
not full speech acceptance. See [implementation and limits](VOICE_BYOL_EVIDENCE_IMPLEMENTATION.md).

**2026-11-09 reviewed-text checkpoint:** immutable case/report binding and a
source-linked browser companion are implemented behind a default-off staging
flag. Each read revalidates consent, current sources and the actual independent
human release decision. This implements the exact-report display branch of FR11
and FR16; it is not live captions or external insurance speech. Changed reports
or human decisions require a new voice session. See
[contracts and evidence](VOICE_CASE_BINDING_IMPLEMENTATION.md).

**2026-11-08 human-review checkpoint:** FR17/FR18 and AC13/AC14 now have an
implemented customer request/status workflow, independent of voice minutes, payment
and microphone consent. A successful response confirms an immutable queued request,
not human contact, notification or approval. An authorized operator can inspect the
bounded intake API and use the existing audited assignment workflow. Every newer
request requires a fresh report-bound human decision before release. Creation is
disabled by default pending migration 015 and a durable Clerk staging rollout;
existing requests continue to enforce holds when creation is disabled. Provider
tool invocation, genuine human operations and live transfer acceptance remain open.
See [the implementation evidence](VOICE_HUMAN_REVIEW_IMPLEMENTATION.md).

**2026-11-08 implementation update:** managed lifecycle APIs/worker, mounted private LiveKit
development UI, current-report/follow-up evidence tools, consented encrypted report excerpts,
signed test billing and gated test-period spending/rollover are implemented. Customer calls
and paid billing remain disabled. This does not close live-provider or all V3?V5 acceptance.
The earlier 401/invalid-agent and unmounted-control statements are historical; account reads
passed on November 7. See [the phase implementation checkpoint](VAANI_PHASES_IMPLEMENTATION_20261108.md)
for exact completed work, tests, deviations and remaining software/approval gates.


**Operational follow-up:** local Docker/migrations and temporary public ingress are verified;
independent V2b media/consent/reconnect controls are implemented but unmounted. No real speech,
provider stop, billing or grounded-insurance acceptance is claimed. Current evidence:
[Docker/tunnel report](VAANI_DOCKER_TUNNEL_REPORT.md).

**V2a addendum, 2026-11-07:** disabled real-provider adapter, signed synthetic usage events and
authenticated synthetic-only BYOL controls are implemented. No customer audio/paid product or
insurance-answer acceptance is claimed. Current requirement/acceptance deltas and evidence:
[V2a report](VAANI_V2A_IMPLEMENTATION_REPORT.md). V1 rows remain historical where indicated.

**Document:** FS-VOICE-001 · **Version:** 1.2 · **Date:** 2026-11-07\
**Status:** V1 hardened and V2a backend controls implemented/tested; live behavior remains gated. Full per-requirement/test status is in [the implementation report](../VOICE_IMPLEMENTATION_REPORT.md).\
**Companion:** [Technical spec](VAANI_VOICE_TECHNICAL_SPEC.md). This file defines user behavior and acceptance; the companion defines implementation.

## Goal

Let a signed-in Assurely customer discuss an authorized health-insurance case in a natural browser conversation, understand clauses and need-fit trade-offs, and explore supported expense scenarios with visible evidence. Optional paid voice should improve understanding while keeping core comparison, safety information and required human review accessible without a voice subscription.

The guide identifies itself as AI. Qualified humans retain policy approval and case-review authority. An AI conversation cannot remove a delivery hold, approve policy data or promise an insurer's decision.

## User stories

| Actor | Need | Intended outcome |
|---|---|---|
| Customer exploring an owned case | Ask questions and follow-up questions by speaking | Understand the policy evidence without navigating every clause alone |
| Customer comparing policies | Ask how a difference affects their stated needs | See sourced, conditional trade-offs rather than a sales recommendation |
| Customer planning claim expenses | Try a permitted financial scenario | See verified inputs, assumptions and a deterministic breakdown |
| Customer reporting a sales statement | Ask whether a statement matches the policy | Receive supported, contradicted or not-verifiable status with evidence |
| Customer whose case needs review | Request a real human | Reach the existing authorized review workflow without buying voice minutes |
| Customer buying optional voice access | Know the allowance, renewal and cancellation terms | Control spending without unexpected overage charges |
| Authorized operator | Investigate usage and delivery failures | Reconcile calls and credits without accessing unnecessary conversation content |

## Scope and current position

This is an extension of Assurely's existing health-insurance application. The screenshots supplied by the user define the document structure; their example authentication technology and requirements are not adopted as product requirements. Clerk remains the identity provider.

| Capability | Repository position on 2026-11-06 | Required outcome |
|---|---|---|
| Sign-in and private application | Clerk integration exists; complete account-level voice acceptance remains pending | Each voice operation belongs to the verified customer |
| Private voice demo | Implemented as a fixed-text, synthetic, no-audio prototype | Remain visibly distinct from live voice |
| Test allowance, reservation and ledger | Implemented for allowlisted test identities | Extend to verified subscription periods and provider reconciliation |
| Voice consent receipts | Separate purposes and versions exist | Enforce current consent throughout actual processing and revocation |
| Browser audio and Vaani | No real call integrated | Establish and end a real synthetic-data call before customer release |
| Insurance answers and calculations | Existing advisory foundation; demo uses fictional canned answers | Permit only verified, authorized evidence and supported calculators |
| Subscription checkout | Not implemented | Signed billing events control entitlements |
| Captions, summaries and human transfer | Not implemented for voice | Implement only with consent, authorization and tested provider capabilities |

**Configuration check (current):** Vaani API key is present with valid local formatting, but bounded account authentication still fails; Agent ID is a placeholder. Distinct private ingress credentials exist. Customer voice remains disabled. Temporary public transport checks passed; genuine provider/audio acceptance is still pending.

**V1 implementation note:** synthetic starts now require a separate `voice_demo` consent for demo session/simulated-usage records; withdrawal closes open demos. It grants no microphone or vendor-processing permission. Durable start/end receipts, recovery deadlines, worker cleanup and balance checks are implemented for mocks. A mock passing a criterion does not close that criterion's real audio/billing scope.

## Requirements

“Must” is mandatory for the applicable phase. “Conditional” means the capability stays unavailable until its stated dependency is verified. Requirement completion requires the acceptance evidence below; a selectable language label or mock response is not speech verification.

### Access, disclosure and consent

| ID | Requirement | Delivery phase |
|---|---|---|
| FR01 | Only signed-in users can start, inspect, resume or end their own voice sessions. Another customer's case, conversation, sources and usage remain inaccessible. | V1, reverify V2–V5 |
| FR02 | Show “I am an AI insurance guide” before starting and speak an equivalent disclosure at connection. Explain that guidance is not human professional approval or a claim decision. | V1 text; V2 spoken |
| FR03 | Obtain separate explicit permission for browser microphone and third-party voice processing. Explain unavoidable speech processing separately from optional saved transcripts, recordings and summaries. Sign-in does not grant these permissions. | V2 |
| FR04 | Let users withdraw consent. Withdrawal prevents new affected processing and ends affected active processing with a clear outcome. Explain any mandatory billing/audit retention and any provider deletion still pending. | V2/V5 |

### Starting and managing a conversation

| ID | Requirement | Delivery phase |
|---|---|---|
| FR05 | Offer “Talk to Assurely AI” from eligible comparison/result and case-detail views. Before connection, show the selected case, verified capability status, allowance and call limit. Held cases expose only review status and safe general assistance. | V2/V3 |
| FR06 | Handle microphone denial, unsupported browser, missing audio device and permission changes with usable guidance and a return to text. Avoid starting a provider call when microphone readiness is already known to have failed. | V2 |
| FR07 | Provide start, end and mute/unmute controls; show connecting, listening, processing, speaking, reconnecting and ended states. Muting must not be described as a billing pause. Offer a true pause only if verified to suspend the provider session and usage. | V2 |
| FR08 | Support clarification, interruption and repeated or slower explanations without losing the authorized case context. Show live captions only where verified and permitted. Label partial speech recognition clearly. | V2/V3 |
| FR09 | Offer English and Hindi only after testing each deployed voice pipeline. Offer Hinglish/code-switching only after separate testing. Unsupported choices remain unavailable with an explanation. | V2/V5 conditional |
| FR10 | Recover the same active session after permitted reload/reconnect, with accurate remaining allowance. A retry must not create an extra charge or duplicate call. End calls at the enforced duration limit and confirm uncertain termination accurately. | V2/V4 |

### Evidence and insurance explanations

| ID | Requirement | Delivery phase |
|---|---|---|
| FR11 | Explain only facts applicable to the owned case and permitted by current evidence/release controls. Each factual claim must have a source, document/version or clause reference, verification status and last-verified date visible beside the conversation. Provide a short spoken reference and a way to open the authorized source. | V3 |
| FR12 | Explain co-payment, deductible, room rent, sub-limits, waiting periods, PED, exclusions, premium conditions and claim procedures only to the extent verified for the policy and scenario. Clearly distinguish user statements, estimates, assumptions and verified facts. | V3 |
| FR13 | Explain comparison differences in need-fit language with applicable conditions. Never invent premiums, limits, policy names, legal requirements or coverage guarantees. | V3 |
| FR14 | Offer expense scenarios only when the requested calculation is implemented and supported by verified applicable policy inputs. Show inputs, exclusions from the model, deduction order, assumptions and a deterministic breakdown; describe the result as an estimate, never a promised payout. Unsupported scenarios return missing requirements rather than guessed arithmetic. | V3 conditional |
| FR15 | Treat an alleged sales statement as user-reported. Compare it against applicable evidence and return supported, contradicted or not verifiable, with relevant conditions. Do not infer legal fraud from a limited conversation. | V3 |
| FR16 | When evidence is missing, conflicting, expired, inaccessible or unreviewed, explain that the claim cannot be verified and offer a safe next step. A held report must remain unavailable through speech, captions, tool results, summaries and reload. Recheck access when the case changes during a call. | V3 |

### Human review

| ID | Requirement | Delivery phase |
|---|---|---|
| FR17 | Let the user request an actual authorized human through the existing case-review process. If live transfer is not configured, confirm only a successfully created review request and show its status. A transfer-connected event is not an approval. AI cannot assign itself a human role or decide a review. | V3 |
| FR18 | Voice subscription, remaining minutes and payment status must never prevent required escalation, urgent safety guidance or access to existing permitted text assistance. Do not imply emergency or claims-resolution services the product cannot provide. | V3/V4 |

### Subscription and usage

| ID | Requirement | Delivery phase |
|---|---|---|
| FR19 | Show reviewed plan price/currency/tax disclosure, included voice allowance, renewal terms, cancellation behavior and any usage rounding before checkout. Do not advertise unlimited access or invent a price. | V4 |
| FR20 | Grant paid access only after confirmed billing state. Show allowance and call limits before a call and usage afterward. Reserve allowance so two concurrent starts cannot spend the same minutes. No automatic overage charges. | V1 mock; V4 paid |
| FR21 | Handle exhausted allowance, inactive subscriptions, failed renewals, cancellation and period transitions predictably. Cancellation at period end preserves access until that verified end date; immediate suspension blocks new calls. Existing calls follow the disclosed, bounded active-call policy. | V4 |
| FR22 | Retry and abnormal termination must not double-charge. Failed pre-connection calls release confirmed unused allowance. Uncertain provider usage is shown as pending reconciliation, with a final adjustment when verified. | V2/V4 |

### History, privacy and usability

| ID | Requirement | Delivery phase |
|---|---|---|
| FR23 | On end, show duration, usage and an optional consented recap containing answered/unresolved questions and authorized references. Recheck access before displaying a saved recap. Do not save raw audio by default or retain an optional transcript/summary after its consent is absent. | V3/V5 |
| FR24 | Provide keyboard-operable, labeled controls, meaningful status announcements, responsive phone layouts and a text alternative. Test at 360px width, 200% zoom and on actual mobile devices. Do not rely on color or animation alone. | V2/V5 |
| FR25 | Make failures understandable: tell the user whether audio connected, whether ending is confirmed, whether usage is pending, and how to continue safely. Operators can investigate using event/session references without exposing secrets or sensitive speech in logs. | V2–V5 |

## Acceptance criteria

Each criterion is a release test, not a claim that a test has run. The technical spec maps these IDs to layers and evidence.

| ID | Given / when / then | Requirements |
|---|---|---|
| AC01 | **Given** a signed-out user, **when** they open a private voice page or call a voice API, **then** the page requires sign-in and the API returns unauthorized without session data. | FR01 |
| AC02 | **Given** customer B knows customer A's voice/case identifier, **when** B reads, reconnects, ends or requests sources/summary, **then** no A data or provider credential is returned. | FR01, FR11, FR23 |
| AC03 | **Given** a permitted start, **when** audio connects, **then** AI disclosure is visible and spoken before insurance guidance; the test recording/transcript confirms it. | FR02 |
| AC04 | **Given** missing or revoked required voice consent, **when** start or an active turn is attempted, **then** affected processing does not proceed; a saved-summary refusal does not grant unrelated retention. | FR03, FR04 |
| AC05 | **Given** denied microphone permission or an unsupported device, **when** the user starts, **then** actionable text appears, text assistance remains usable, and no avoidable provider dispatch/usage occurs. | FR06, FR25 |
| AC06 | **Given** an active call, **when** mute, interrupt and end are used, **then** microphone sending, speech interruption, call state and confirmed termination match the displayed controls. Mute does not falsely freeze the usage display. | FR07, FR08 |
| AC07 | **Given** the per-language test set, **when** native/proficient reviewers test follow-ups and financial terminology, **then** the enabled language passes the technical thresholds; untested Hinglish remains unavailable. | FR09 |
| AC08 | **Given** a network drop/reload, **when** the user reconnects within the supported window, **then** the same server-owned call is recovered or a clear ended/pending status is shown; no duplicate dispatch or debit occurs. | FR10, FR22 |
| AC09 | **Given** verified applicable clause evidence, **when** the customer asks a follow-up, **then** every factual assertion matches that evidence and an authorized citation with last-verified date is visible. | FR11, FR12, FR13 |
| AC10 | **Given** a supported expense scenario, **when** the same inputs are submitted repeatedly, **then** the numeric result and deduction breakdown match the deterministic reference fixture; missing policy fields prevent an unsupported result. | FR14 |
| AC11 | **Given** a sales statement that omits a condition, **when** it is checked, **then** the response preserves the condition and does not mark the broad statement supported. | FR15 |
| AC12 | **Given** a delivery hold or newly revoked evidence, **when** any voice, caption, tool, source or summary path runs or reloads, **then** held material is absent and the allowed review-status response remains available. | FR16 |
| AC13 | **Given** an ambiguous case, **when** a human is requested, **then** either an actual configured transfer or one idempotent review request is confirmed. No AI/provider event creates an approval or clears a hold. | FR17 |
| AC14 | **Given** no subscription or zero voice minutes, **when** required human review is requested through the existing workflow, **then** payment is not required. | FR18 |
| AC15 | **Given** successful browser checkout text without a valid server billing event, **when** voice is started, **then** paid entitlement is not granted. A verified event grants only the correct plan and period. | FR19, FR20 |
| AC16 | **Given** allowance for one permitted call, **when** two distinct starts arrive concurrently, **then** only the permitted reservation succeeds and counters remain nonnegative and within allowance. Repeated identical requests return the same session. | FR20 |
| AC17 | **Given** cancellation, failed renewal or a period boundary, **when** a new call is requested, **then** access follows verified effective dates and existing reservations stay attached to their original period. | FR21 |
| AC18 | **Given** duplicate, reordered, forged or delayed events and a missing terminal event, **when** events/reconciliation run, **then** usage settles once or stays explicitly pending; invalid events never grant access. | FR22 |
| AC19 | **Given** no summary/recording consent, **when** a call ends and history is opened, **then** optional content is not stored or shown. With summary consent, only an authorized cited recap is returned. | FR03, FR23 |
| AC20 | **Given** keyboard, screen-reader, 360px mobile and 200% zoom checks, **when** the journey is completed, **then** controls remain operable and status/errors readable without layout obstruction. | FR24 |
| AC21 | **Given** vendor failure, timeout or an attempted instruction override, **when** a turn is processed, **then** no unverified answer or secret is spoken and a bounded safe outcome is shown. | FR16, FR25 |
| AC22 | **Given** an eligible owned result or case view, **when** voice is opened, **then** the selected case, capability status, remaining allowance and enforced call limit are shown before connection. For a held case, only permitted general/review assistance is offered. | FR05 |
| AC23 | **Given** an offered subscription, **when** the user reviews checkout and cancellation, **then** the approved price, applicable tax, renewal date, allowance, rounding and cancellation behavior are disclosed consistently; no unapproved price or overage is charged. | FR19, FR21 |

## Out of scope for this feature

- Outbound/inbound telephone calls, campaigns, WhatsApp and automatic dialing.
- Life-insurance voice, cross-customer/family shared calls and unrestricted document uploads to Vaani.
- Automatic policy purchase, underwriting, guaranteed claim approval, legal certification or AI replacement of qualified review.
- Voice cloning or a voice that impersonates a named human.
- Saved raw recordings, cross-call profile memory and training on customer conversations by default.
- Unreviewed retail prices, production charges, unlimited calls and background overage purchases.

## Open questions and dependencies

| ID | Decision needed | Default until resolved |
|---|---|---|
| OQ01 | Which owned development agent, selected STT/TTS voices and Vaani workspace will be used? | Real-call start unavailable; key presence alone is insufficient |
| OQ02 | What provider data/recording retention can the account actually disable, and what processing is unavoidable? | Synthetic data only; no customer medical information |
| OQ03 | Can dispatch calls be forcibly ended and reconnected with verified server controls, or must the documented managed-session flow be used? | No paid live release without bounded termination |
| OQ04 | What are the actual provider billing pulse, taxes, component rates and cancellation/refund terms? | No retail price or production plan |
| OQ05 | Which merchant account/provider and approved plan terms will be used? | Razorpay is a candidate; checkout stays unavailable |
| OQ06 | Which policy versions/calculator capabilities and authorized human reviewers have production acceptance? | Unsupported estimates and held recommendations stay unavailable |
| OQ07 | What summary retention/deletion periods and vendor/privacy terms are approved? | Optional persistence off |
| OQ08 | Does the account support authenticated BYOL and cancellation of obsolete turns without an unsafe fallback? | No real-policy speech until demonstrated |

## Delivery and review order

1. **V0:** maintain provider research and these two specs with explicit evidence boundaries.
2. **V1:** mock lifecycle gaps closed and tested in this item; retain synthetic/no-audio labels and use the implementation report's acceptance boundaries.
3. **V2:** one genuine synthetic-data WebRTC call, authenticated events, termination, reconnect and language measurements.
4. **V3:** authorized Assurely evidence/tools, verified calculation capabilities, speech safety and actual human-review request handling.
5. **V4:** test-mode billing and period-aware reconciliation with reviewed prices; no production charging during implementation tests.
6. **V5:** privacy/vendor, verified-source/calculator, human-operations, accessibility, security and reliability evidence before controlled customer release.

Changes to these behaviors require updating matching technical decisions and acceptance criteria before implementation. Repository unit/build success alone does not close real audio, language, billing or qualified-review acceptance.

## References

- [Requested feature blueprint](ASSURELY_CLERK_VAANI_CODEX_PROMPTS.md), PROMPT 2.
- [Implementation report](../VOICE_IMPLEMENTATION_REPORT.md) and [progress](../PROGRESS.md); historical test counts are not new acceptance results.
- Current vendor contracts, code paths and research evidence are listed in the [technical spec](VAANI_VOICE_TECHNICAL_SPEC.md).
