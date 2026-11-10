# Assurely: Clerk Authentication + Vaani Premium Voice Advisor

**Agent-ready implementation prompts** | Research checked: 2026-11-03\
**Status:** Product/design instructions, **not** a statement that these features are already implemented.

> **Non-negotiable:** A human-like **AI voice guide is not a qualified human reviewer**. It must clearly identify itself as AI; cannot sign off insurer data, certify calculator assumptions, override an escalation hold, or impersonate licensed professionals. A separate human approval/handoff workflow remains mandatory whenever the system's controls require it. Do not put safety-critical human review or honest risk disclosures behind a subscription paywall.

## Grounding and implementation caveats

- Existing architecture according to prior Assurely project reports: Next.js 16 App Router UI; FastAPI backend; Postgres and Redis; LangGraph stages for intake, intent routing, health-domain RAG, deterministic risk analysis, compare/verify, guardrail, explanation report, escalation and persistence; Langfuse tracing; existing JWT/JWKS verifier; consent-gated profile memory; existing frontend/API contract gaps. **Verify every statement against the current repository before editing.**
- Clerk documentation: https://clerk.com/docs/nextjs/getting-started/quickstart ; https://clerk.com/articles/how-to-add-authentication-to-a-python-backend ; https://clerk.com/docs/guides/sessions/manual-jwt-verification ; https://clerk.com/docs/guides/sessions/session-tokens
- Vaani: https://www.producthunt.com/products/vaani-developer-platfrom ; https://www.vaani.dev/developers ; https://docs.vaani.dev/api-reference/trigger-call ; https://docs.vaani.dev/guides/webhook-setup ; https://docs.vaani.dev/llms.txt ; https://www.vaani.dev/pricing
- Vaani public API currently documents `POST https://api.vaanivoice.ai/api/trigger-call/` with `medium="webrtc"`, returning a session token, room name and connection URL. Vaani's docs also describe provider key via `X-API-Key`, a LiveKit/WebRTC connection, optional `live_captions_url`, and `call_postprocessing` events. **Inspect current documentation and the current provider account before coding.** Never place `VAANI_API_KEY` in browser code.
- Vaani's published pay-as-you-go **platform** fee is ₹1/minute **plus applicable** model, STT, TTS and other usage fees. Its example calculator currently illustrates ~₹5.66/minute for one particular stack with telephony, not a fixed quotation. WebRTC browser voice does not have a telephony charge, but other components remain billable. Public self-serve pricing lists **30-day data retention**; verify vendor contract, DPDP obligations and data processing before sending personal/health data.
- Clerk Billing only supports Stripe as the payment processor per its public docs. Razorpay Subscriptions is a possible India-focused alternative. **No payment processor has been chosen yet**. Design a provider-agnostic entitlement boundary and do not invent pricing.
- At minimum inspect `docs/`, `PROGRESS.md`, environment-variable **names only**, and real code. Preserve existing modules/migrations/UI and do not wholesale rewrite architecture.

---

# PROMPT 1: Integrate Clerk Auth into Assurely (Next.js + FastAPI)

You are a senior Next.js/FastAPI authentication, identity-security, and migration engineer working in the existing **Assurely** repository.

## Decision already made

Use **Clerk** as our user identity provider. This is NOT an invitation to rebuild our backend or remove the existing safety workflow. Our Next.js 16 App Router front end and FastAPI application already have routes, schema/migration history, consent gates, decision traces and JWT verification code. Your job is to securely connect Clerk to these components, preserve existing data and make the app usable from browser to backend.

## First action: audit, not assumption

Read the latest `docs/`, `PROGRESS.md`, relevant front-end sign-in/sign-up/intake/session and API-client files, `app/core/security.py`, authentication dependencies, `users`, `sessions`, `consent_records`, `user_profile_memory`, `escalations`, `audit_log`, `decision_trace` models and Alembic migration history. Do not print or reveal any secret .env values. Create a factual `AUTH_INTEGRATION_AUDIT.md` documenting existing routes/contracts and any migration risks. Inspect whether another auth provider or real users already exist; if yes, propose a reversible migration and preserve their identities and data rather than destructively switching providers.

## Design and implementation requirements

1. **Frontend Clerk:** Follow current Clerk/Next.js 16 docs (especially `proxy.ts` naming; do not blindly create the older `middleware.ts`). Use official `@clerk/nextjs`, `ClerkProvider`, server-side auth checks, sign-in/up, user profile, sign-out, loading/error states and protected routes. Keep Assurely's existing look. Keep landing and public educational routes public. Do not assume `clerkMiddleware` automatically protects routes; explicitly protect private views and server APIs.
2. **Authenticated FastAPI requests:** The browser (or secure Next.js server proxy) must attach a real Clerk session token on each private backend API call. The FastAPI backend must **independently** verify signature, expiration, not-before, expected issuer and authorized party/origin; validate `aud` only when using a token/profile that actually supplies the intended audience. Use Clerk's supported Python backend auth flow / correctly verified RS256 JWTs + JWKS public keys with caching/rotation. Reject token substitution, arbitrary JWT algorithms, expired tokens, mismatched origins and missing credentials. Keep local test-mode auth clearly separate and unavailable in production.
3. **Identity mapping:** Bind Clerk's immutable `sub`/user ID to one stable local user identity. Add unique indexes/migrations where required. Never trust `user_id` posted by the browser. Map existing consent, case/session history, decision traces, profile-memory snapshots and escalation ownership to the authenticated user. Preserve history. Consider privacy-conscious email handling.
4. **RBAC (role-based access control):** Distinguish `customer`, `admin`, `qualified_policy_reviewer`, and `human_advisor` permissions. These roles/UUID mappings must be granted only by trusted server/admin flows, not through user-editable profile metadata. Reviewer may validate source facts/calculator assumptions; advisor can review assigned escalations; customer sees only their own cases; admin controls operational settings. Use fine-grained permissions, not a generic 'logged-in=true'. Approval records require authenticated reviewer ID, decision time, exact document version/hash, rationale, and audit trail. Test accounts cannot grant production approval.
5. **Consent:** Keep DPDP-oriented consent separate from authentication. A successful Clerk sign-in is NOT consent to health-data processing, profile memory, audio recording, transcript retention or external vendors. Provide distinct versioned purpose-specific consent requests and clear grant/revoke flows. Verify each purpose server-side.
6. **Session continuity:** Fix frontend/backend API contract mismatches after inspecting real models; previous reports suggested `user_message` vs `content` and `reply` vs frontend expectations. Ensure `/v1/message`, session history, comparisons, consent and profile endpoints work end-to-end. Test page reloads and backend restart, recognizing that LangGraph `MemorySaver` in-process checkpoints are different from persistent user memory; document or address persistent checkpoint durability.
7. **Error handling and security:** Fail closed on auth service unavailable/misconfiguration. Proper 401/403 differentiation; no leaked JWTs, token logs, open redirect, excessive user data, unauthenticated websocket, insecure CORS, or cross-tenant access. Protect both API routes and direct backend endpoints. Add log redaction and audit events for reviewer/admin actions.
8. **Configuration:** Document exact, non-secret names only (for example Clerk publishable and secret keys, trusted issuer/JWKS URL, frontend origin allowlist and optional role mappings), how to obtain them from the provider dashboard, and dev/staging/prod setup. Keep runtime secrets server-side, no hardcoded fake production values. If integrating the Clerk CLI, first confirm existing auth and plan non-destructive migration; do not overwrite arbitrary existing files.
9. **Vaani-readiness:** Provide a reusable backend `AuthenticatedPrincipal`/user context and authorization dependencies for premium voice sessions, reviewer actions and billing events. Do not make voice entitlements depend solely on Clerk's frontend UI.

## Tests and evidence

Create unit/integration/browser E2E coverage for sign-up/login, logout, expiry, invalid signature, wrong issuer/authorized party, refresh, cross-account access, anonymous access, customer cannot approve, reviewer cannot impersonate admin, revoked consent, session restore, and delivery hold on refresh. Run tests/build with captured commands/results. Add a small architectural sequence diagram and operator setup guide. Only report as done what actually works; distinguish mocked integration from real provider verification.

## Deliverables

- Minimal well-tested code changes; any Alembic migrations; `.env.example` without secrets; updated auth docs.
- Route/authorization matrix and Clerk-to-local-user mapping contract.
- `AUTH_IMPLEMENTATION_REPORT.md`: implemented / deferred / blocked (keys or human review) / exact next steps.
- A working browser-to-FastAPI login & protected advisory flow in dev using genuine configured Clerk dev credentials if they exist; otherwise an honest tested stub plus clear setup instructions.

Proceed incrementally: audit -> proposed changes -> auth integration -> secure API mapping -> tests -> report. Do not invent role UUIDs or claim a test reviewer is licensed.

---

# PROMPT 2: Build a subscription-based Vaani AI Voice Insurance Guide without bypassing human approval

You are a senior real-time voice AI, FastAPI/LangGraph, safety, billing and UX engineer working in the existing **Assurely** codebase. We want a **premium in-app voice conversation** that allows a signed-in user to explore a specific health-insurance comparison, ask detailed follow-up questions and understand actual costs. Use Vaani as the primary candidate after a technical spike. **This AI guide must NOT replace the independent human review checkpoint.**

## Product vision

Assurely's main experience remains evidence-based text/visual comparison. Add an optional **"Talk to Assurely AI"** voice action on the comparison/result and case-detail views. User starts a browser voice conversation, in Hindi, English or Hinglish as supported and tested. Voice responds naturally, allows interruptions and questions, but always discloses "I am an AI insurance guide" early and in the visible UI. Voice can explain relevant clauses, co-pay, deductible, room rent, sub-limits, waiting periods, PED, exclusions, claim procedures, premiums and estimated out-of-pocket expenses **using only evidence permitted by the existing Assurely backend**. It cannot guarantee claims or promise acceptance by an insurer.

## Research and spike FIRST

1. Read https://www.vaani.dev/developers , https://www.vaani.dev/pricing , https://docs.vaani.dev/llms.txt and linked **current** WebRTC, BYOL, SDK, webhook, agent-training and tool/action documents. Verify current account availability, supported languages, browser/WebRTC, LiveKit session token flow, callable tools, transcript options, webhook authentication/signature, concurrency restrictions, latency, recording retention, DPA/security, account-level costs and actual per-minute billing. Record what is **documented**, **verified with real credentials**, or **unknown**. Do not fabricate SDK names or response fields.
2. Spike `POST /api/trigger-call/` with `medium="webrtc"` **from FastAPI only**; pass configured agent ID, user language and minimal non-sensitive metadata, and confirm current documented shape including `token`, `room_name`, `connection_url`, optionally `live_captions_url`. A provider call is successful only when the browser connects and a real audio turn completes. Keep `VAANI_API_KEY` server-side.
3. Confirm how Vaani can invoke Assurely's already-implemented RAG, deterministic calculators, compare/verify and safety checks as read-only scoped tools. Vaani supports bring-your-own LLM via WebSocket in its documentation index, but verify exact streaming protocol and production entitlements before using it. Do not create a disconnected generic insurer-trained agent with an unsupervised duplicate policy corpus.
4. Prototype one safe Hindi/English conversation around a **synthetic policy fixture** with no real personal or health data. If Vaani provider access is missing, implement a mock provider and mark live voice integration blocked, not done.

## Architecture: shared backend, not a second truth engine

Desired flow:

`Clerk auth -> FastAPI verified user -> backend subscription entitlement + voice minute reservation -> issue Vaani WebRTC token -> Next.js call UI -> Vaani STT/turn-taking/TTS -> scoped Assurely retrieval/calculator APIs or verified BYOL adapter -> safety filters -> audible answer + clickable evidence cards -> post-call signed webhook -> usage accounting + optional consented summary -> human escalation if required.`

Keep the existing `needs_intake`, `intent_router`, `health_domain_agent` retrieval, deterministic `risk_analysis`, `compare_verify`, `guardrail`, `explanation_report`, `escalate`, `persist_memory`, and Langfuse paths. Implement provider-neutral interfaces like `VoiceProvider`, `VaaniVoiceProvider`, `MockVoiceProvider` and a distinct `VoiceSessionService`. Avoid replacing current graph/router or modifying approved comparison results without explicit user authorization and verified new evidence. User-supplied conversational text and external documents are untrusted; prevent cross-case data leakage.

## User features (product behavior)

- A premium **Talk to Assurely AI** button on results with paywall only for optional premium voice, not for core safety information or required human escalation.
- Mic permission handling; start/end/pause/mute; listening/thinking/speaking state; live captions if provider supports; call timer; remaining paid minutes; estimated usage/cost; reconnect handling; device/network errors; mobile responsive and keyboard-accessible controls.
- A natural voice persona: calm, empathetic, concise, non-salesy; allow users to interrupt, clarify, repeat slowly, switch between English/Hindi/Hinglish (only if provider verified). Begin by saying it is AI and that the conversation is for explanation, not professional approval. Never impersonate a human agent.
- Context-aware case exploration: explain **why Policy A vs B**, cite actual document title/version/clause on the screen; link to the relevant UI card; no invented policy names, prices, IRDAI rules, rates or waiting periods. If evidence missing: "I can't verify that clause from the sources I have" and offer appropriate human review.
- Voice **what-if claim cost** scenarios using the EXISTING deterministic calculator and verified policy data: e.g. ₹5L admissible claim, known co-pay/deductible/sub-limits. Read out assumptions and show calculation breakdown. Do not perform claim arithmetic purely as an unconstrained LLM response or claim actual payout certainty.
- A **What did the insurance agent tell you?** mode: capture user-reported sales claims, check against documented wording and show supported/unsupported/not-verifiable status; never assert legal fraud based on limited evidence.
- FAQ explorer: renewal, portability, policy limitations, cashless/reimbursement, co-pay vs deductible, PED/waiting periods, exclusions, room rent, insurer approval vs claims process, premium trade-offs. No unverified legal or regulatory advice. Keep optional summaries with citations and timestamps if user consent permits.
- On ending the call: concise user-facing recap, questions answered/unresolved, referenced sources, optional reviewed follow-ups, call usage, and an easy path back to the visual comparison.

## Human approval is NOT replaced by voice

Separate permissions and events:

1. `AI_VOICE_GUIDANCE`: Explain approved facts; optional premium customer feature.
2. `HUMAN_POLICY_APPROVAL`: Qualified reviewer validates sourced policy versions, calculator assumptions, and data quality; mandatory launch gate where required; never AI-signed.
3. `HUMAN_CASE_REVIEW`: Authorized adviser/reviewer evaluates held or uncertain individual cases; may receive an AI-prepared summary, but explicitly makes/records own decision.

An AI voice response cannot clear `delivery_hold`, approve synthetic policy data, write a production approval record, self-assign reviewer status, or expose the held report (even through voice transcript, captions, reload, debug endpoints or post-call summary). Handle human transfer only if an actual configured/authorized destination exists, otherwise create a review request and safely inform the user. A Vaani `human_transfer_successful` webhook indicates a real human connection, **not** approval of a policy/case. Paid minutes must never be a prerequisite for escalation or urgent safety explanations.

## Subscription and cost controls

Design a provider-neutral billing interface; evaluate Razorpay Subscriptions for India and Clerk Billing (Stripe-only) using account eligibility, fees, tax, customer experience and webhook availability. Do not automatically provision production plans or charge any person. Do not invent plan prices or unlimited calls.

Proposed feature flags and entitlements (illustrative, configurable, not hardcoded product promises):
- Free: normal intake, comparison, evidence and safety/human escalation; no voice or optional limited trial.
- Voice Pro: N voice minutes per month, configurable simultaneous call limit and maximum single-call duration.
- Optional additional minutes only after explicit pricing/consent; no surprise overage bills.

Server, not client, is source of truth for: subscription status, user voice credits/allowance, call eligibility, minute reservation, concurrent sessions, unique call IDs, idempotent usage ledger, webhook reconciliation, usage refunds on failed/unanswered calls, cancellations and downgrades. Use reservation-and-settlement so two simultaneous calls cannot double-spend a monthly quota. Compute provider billing pulses, taxes and margin in a documented profitability model. Privacy-aware plan transitions and failed billing handling. Set hard provider budget and concurrency limits.

## Proposed domain model (rename to match actual code)

- `voice_sessions`: UUID, user_id, case_id/session_id, provider, provider_call_id, room_id, state, language, started/ended, amount reserved/consumed, consent snapshot, error category, trace IDs.
- `voice_usage_ledger`: unique settlement reference, seconds/minutes billed, reservation/release/debit, source webhook, created_at, idempotency key.
- `subscription_entitlements`: verified provider subscription, plan, effective/cancel dates, monthly allowance, concurrency limit, status.
- `voice_conversation_artifacts`: optional minimized transcript/summary pointers, evidence IDs and deletion/retention metadata; never persist raw audio by default.
- `human_review_requests`: existing escalation link, priority, assigned actual reviewer, case state; do not duplicate existing tables unnecessarily.

All state rows must be owner-scoped, time-bounded and traceable; add Alembic migrations and indexes only after reviewing schema. External IDs remain separate from internal UUIDs. Version/consent associations accompany evidence and case data.

## Backend APIs (illustrative contracts; adapt to existing API conventions)

- `GET /v1/voice/entitlement`: remaining minutes, active plan, capability/region and constraints.
- `POST /v1/voice/sessions`: authenticated user + valid subscription + eligible case + consents + concurrency gate -> reserve allowance, initiate provider session server-side, return short-lived browser connection material only.
- `POST /v1/voice/sessions/{id}/end`: idempotent user-initiated end; actual settlement uses verified call event/state.
- `GET /v1/voice/sessions/{id}`: owner-only state + optional transcript/summary availability.
- `POST /v1/webhooks/vaani`: verify provider's documented authenticity scheme; reject forged/replayed events; idempotently process `call_started`, `call_ended`, `call_postprocessing`, `call_failed`, and human-transfer events. Carefully account for `call_duration` units: Vaani docs indicate **seconds** for `call_ended` but **milliseconds** inside `call_postprocessing` payload.
- `POST /v1/webhooks/billing-provider`: signed checkout/subscription webhook -> entitlement state transition. Never trust browser "payment succeeded" flags.

Use separate scoped internal tools like `get_verified_policy_clause(case_id, policy_id, topic)`, `explain_comparison(case_id)`, `simulate_claim_cost(case_id, input)`, `get_evidence_metadata(case_id)` and `request_human_review(case_id, reason)`. Validate all args and permissions. Tool output must carry citation IDs, source version, verification status, assumption flags, and safe-for-speech fields; reject synthetic/unverified policy clauses for real-world claims.

## Safety, privacy and compliance

- Clearly mark AI; do not simulate a human professional. No policy guarantees, no fake claim approval, no guaranteed premiums/payouts. Escalate uncertainty, conflicting clauses, emergency medical/claim disputes and unsupported decisions to an actual human where appropriate.
- Explicit granular consent for microphone use, third-party voice processing, recording (if on), transcription/retention, analytics and profile memory. Keep sign-in consent separate. Implement revocation, retention and deletion handling; verify Vaani's publicly described standard 30-day retention and enterprise zero-retention options with vendor before sending sensitive data.
- Minimize or pseudonymize payloads to Vaani. Never include raw medical history, passwords, full user profiles, full insurance documents or secret URLs in public WebRTC metadata. Never log API keys or transcripts in plaintext. Browser never receives Vaani API key. Protect recordings and post-call history with per-user authorization.
- Prompt injection protection across user speech, external policy documents and tool responses; tool invocations permission-checked server-side. Rate limits, provider timeouts, retry budgets, network recovery and fail-closed delivery. Do not assume TTS voice output is safe simply because text is safe: verify final spoken content policy.
- Voice content should not be used as human reviewer approval; authorized humans must perform review using separately recorded actions and audit evidence. Verify legal, insurance distribution and DPDP launch requirements with a qualified person before offering regulated advice or processing real users' sensitive data.

## Observability and testing

Link voice session IDs, Vaani call IDs, case/decision trace IDs and Langfuse spans. Instrument latency (P50/P95), interruption behavior, cost/min, tool success, source-grounding, escalation/hold events, minute reconciliation and language-quality metrics. Scrub sensitive content; no uncontrolled raw audio logs.

Must implement/verify tests for: valid and invalid Clerk sessions; free user cannot start premium call; subscription cancelled mid-call; monthly allotment exhausted; concurrent starts; replayed webhook; inconsistent call duration units; Vaani API down; microphone denied; low bandwidth; Hindi/Hinglish speech; interruption; ambiguous policy clause; attempted voice jailbreak; user requests secrets/another user's case; human-review hold; source citation inaccessible; recordings/transcripts disabled by consent; reload/post-call endpoint cannot leak held recommendation; call ends abnormally; retry without duplicate billing. Include unit/integration/E2E plus a real Vaani spike if credentials are available.

## Implementation phases and exit criteria

- **V0: Audit + docs**: current codebase audit, provider due diligence, data processing / costs, architecture & threat model. No paid live features yet.
- **V1: Mock vertical slice**: Clerk dev user -> test entitlement -> mock voice provider -> mock call UI -> safe context-bound answer -> session ledger -> tests.
- **V2: Real Vaani WebRTC**: server creates WebRTC connection, browser connects, one real synthetic-data call, live captions if supported, secure post-call webhook and verified billing units.
- **V3: Assurely tools integration**: RAG + calculators + citations + hold enforcement + human case review; regression and adversarial tests.
- **V4: Subscription integration**: chosen provider test-mode checkout, signed webhook, entitlements, quota/reservations, costs and monthly reset tests.
- **V5: Launch gates**: verified policy data and assumptions, qualified reviewer operational workflow, privacy/vendor agreement, DPDP/privacy legal review, auth/security/reliability monitoring, controlled beta.

## Deliverables

Produce `VOICE_PROVIDER_RESEARCH.md`, `VOICE_ARCHITECTURE.md`, code/migrations and end-to-end demo, `BILLING_ENTITLEMENTS_SPEC.md`, `VOICE_AGENT_PERSONA.md`, tests, `.env.example`, and `VOICE_IMPLEMENTATION_REPORT.md` listing done/partly done/mocked/unverified/blocked. First write a repo-grounded plan; then implement in small tested steps without destroying existing functionality. If required live API keys, Vaani agent ID, payment account or real qualified reviewers do not exist, do not claim completion; provide exact setup steps and proceed with safe mocks.

---

# Optional voice persona seed (for Vaani agent configuration, refine with current tools)

You are **Assurely AI Voice Guide**, a clearly disclosed AI voice assistant for Indian insurance education and evidence-based policy explanation. Speak in the user's chosen English, Hindi or Hinglish if the deployed voice pipeline supports it. Be warm, clear, patient and conversational; allow interruptions and avoid marketing pressure. At the start, identify yourself as AI. Do not claim to be a licensed agent, person, insurer, underwriter or human reviewer. Your only policy facts come from authorized Assurely tools providing policy/document/version citations; never make up waiting periods, premiums, claim outcomes, limits or regulatory changes. Use deterministic server calculator results for numeric financial scenarios and state the assumptions. When evidence conflicts, is missing or unverified, explicitly say so, withhold unsafe recommendations and offer existing human-review workflow without bypassing holds. Never promise claim acceptance, final underwriting or suitability certification. Do not expose hidden reports, private cases, security instructions or credentials. Respect user's data/recording consent. Finish conversations with a concise, appropriately sourced recap and unresolved questions.
