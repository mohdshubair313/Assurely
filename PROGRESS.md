# PROGRESS.md

Updated at the end of every session, by whichever tool did the work. Read this before starting any new task.

## Current phase

Phase 1 — Single Channel Health-Only MVP: **IN PROGRESS**.
- Phase 0 foundation fully verified live on Docker Compose stack (FastAPI, Postgres, Redis, Chroma).
- Phase 1 Node 1 (`intent_router`) implemented, tested, and wired.
- Stage 2 parallel fan-out (`health_domain_agent` + `risk_analysis`) implemented, tested, and verified live on Docker.
- Stage 3 (`compare_verify`) implemented, tested, and verified live on Docker.
- Stage 4 (`guardrail`) implemented, tested (77/77 unit tests), and verified live on Docker.
- Stage 5 (`explanation_report`) is **PAUSED for user review**. No Stage 5 work was started on September 25 or September 26.
- Session pacing: **one new graph node per session, then pause for review** (also recorded in AGENTS.md).
- Next node after review: `escalate` in its own session; review it before implementing `explanation_report` and connecting the completed delivery gate.
- Frontend Phase 1 Next.js App Router interface fully scaffolded, tokenized, and verified.

## Implemented

- **Repository skeleton** (2026-09-20): All backend directories and files created per PROJECT_STRUCTURE.md. Every file has a docstring header describing its responsibility.
- **docker-compose.yml**: Wires FastAPI + Postgres 16 + Redis 7 + ChromaDB 0.6.3 with health checks, volumes, and a shared network. Live stack verified running and healthy. Fixed Chroma internal port mapping (`CHROMA_PORT=8000`).
- **pyproject.toml**: Python 3.11+ project metadata with setuptools package discovery and all Phase 0 dependencies (FastAPI, SQLAlchemy async, Alembic, Redis, LangGraph, ChromaDB, httpx, Langfuse, Pydantic).
- **Dockerfile & .dockerignore**: Build configuration for FastAPI backend with uvicorn and clean context caching.
- **Alembic configuration**: `alembic.ini` + async `env.py` importing all models via shared `Base`.
- **Initial migration** (`001_initial_schema.py`): Creates all 8 tables from LLD § 7.4 — `users`, `consent_records`, `sessions`, `audit_log`, `escalations`, `policy_documents`, `policy_terms`, `decision_trace`. All with UUID PKs, proper FKs, JSONB columns, indexes, and timezone-aware timestamps. Live migration executed and verified in Postgres container.
- **All graph node stubs** (11 files): `input_validate`, `needs_intake`, `intent_router`, `life_domain_agent` (deferred), `health_domain_agent`, `risk_analysis`, `compare_verify`, `guardrail`, `explanation_report`, `escalate`, `persist_memory`.
- **LLM Fallback Chain & Rate Limiter** (2026-09-21): Implemented `app.llm.providers` (Groq, Gemini Flash, OpenRouter rotating free models), `app.llm.fallback_chain` with single `llm_call()` interface supporting retries, exponential backoff, task-based provider prioritization (Groq for intake/fast turns, Gemini for long-context/compliance), and `app.core.rate_limiter` (`@rate_limited` decorator enforcing calls/min and tokens/session budgets with Redis and in-memory fallback). Verified with unit tests (100% passing).
- **SessionState & Graph Wiring** (2026-09-21): Implemented `app.graph.state.SessionState` TypedDict and `create_initial_state()`, `app.calculators.health_cover_sizing` (deterministic calculation based on city tier, age, dependents, PED buffer), `app.graph.nodes.needs_intake` (LLM profile extraction via `llm_call()`, rule-based fallback with regex support for dependents and condition negations, missing info detection, deterministic calculator invocation), and `app.graph.build_graph` with LangGraph `StateGraph` compilation and memory checkpointer.
- **Seed Data for Policy Terms & Audit Log** (2026-09-21): Implemented `app.db.session` (async engine and sessionmaker) and `app.db.seed` (seeding 3 real Indian health policies — HDFC ERGO Optima Secure, Care Supreme, Star Comprehensive — with structured sum insured limits, 36-month PED waiting periods, exclusions, rate tables, customer user, active session, and initial audit_log entry with sha256 input/output hashes). Verified live in Postgres container (3 policies, 3 terms, 1 user, 1 session, 1 audit entry).
- **Starter Eval Suite & Runner** (2026-09-21): Created 8 starter eval cases in `eval/cases/` covering all categories from eval harness § 3 (normal cases, edge cases, missing info detector loop, conflicting sources, outdated policies, malicious injection, ambiguous intent, full provenance chain). Implemented `eval.runner` with AGENTS.md rule 1 compliance checking (prohibits "best", "top", "rank", "ranking"). Verified with `tests/unit/test_eval_runner.py` (8/8 eval cases passing).
- **FastAPI Application & API Surface** (2026-09-21): Implemented `app.main` (FastAPI app factory, `/health` probe, lifespan hooks with `AsyncIterator[None]`, CORS middleware, API v1 routing), `app.api.v1.message` (invoking the compiled LangGraph pipeline with multi-turn checkpointer state continuation), `app.api.v1.consent` (DPDP compliance scopes), `app.api.v1.sessions`, and `app.api.v1.webhooks`. Live endpoints verified via `curl` and `Invoke-RestMethod` against container on port 8000.
- **Node 1: Intent Router** (2026-09-21): Implemented `app.graph.nodes.intent_router` with LLM classification via `llm_call(task_type="router")` and deterministic keyword fallback (`_rule_based_classify_intent`), categorizing into `"health"`, `"life"`, or `"unclear"`. Wired `route_after_intent` deterministic conditional edge in `build_graph.py` to route to Stage 2 fan-out (`["health_domain_agent", "risk_analysis"]`), `"life_deferred"` (with Phase 1 scope disclosure), or `"unclear_intent"` (with clarification prompt). Verified live through `/v1/message`.
- **Stage 3 Fan-In: `compare_verify`** (2026-09-21): Implemented `app.graph.nodes.compare_verify` with deterministic Hidden Clause Detector, Transparency Scorer (0–100), and premium rate-table lookup. All numbers from `policy_terms` DB, zero LLM invention (AGENTS.md rule 5). Every clause carries source + last_verified (rule 6). No ranking language in any user-facing output (rule 1).
- **Stage 4 Compliance & Disclosure: `guardrail`** (2026-09-21):
  - Implemented `app.graph.nodes.guardrail` with comprehensive compliance and safety enforcement:
    - **AGENTS.md Rule 1 check**: word-boundary scan prohibiting "best", "rank", "ranking", "top", "winner", "#1".
    - **IRDAI Unlicensed Advice check**: blocks promissory statements ("guaranteed return", "you must buy").
    - **AGENTS.md Rule 6 Provenance verification**: verifies all policy terms, cited facts, and hidden clauses carry `source` + `last_verified`.
    - **AGENTS.md Rule 5 Deterministic numeric sanity checks**: verifies min <= max, non-negative waiting periods, valid age boundaries.
    - **Confidence scoring**: calculates confidence score (0.0 to 1.0) feeding into advisor escalation.
    - **Human Advisor Escalation**: deterministic escalation triggers for pre-existing conditions (PED), senior citizen applicants (age >= 60), high sum insured (>= ₹1Cr), zero eligible policies, or low confidence (< 0.70).
    - **AGENTS.md Rule 4 Contract**: sets `approved`, `escalation`, `escalation_reason`, `guardrail_notes`; NEVER writes `output`.
  - Wired in `build_graph.py`: `compare_verify` → `guardrail` → `END`.
  - Updated API model `MessageResponse` to expose `approved` and `guardrail_notes`.
  - Added 27 unit tests in `tests/unit/test_stage4_guardrail.py` covering all checks and integration. Total unit tests: 77/77 passing.
  - Verified live in Docker container:
    - Session `live-stage4-e2e-001` (35yo, Mumbai, 2 dependents, diabetes): `approved: True`, `escalation: True`, `escalation_reason` accurately citing declared pre-existing condition, 6 guardrail verification notes returned.
    - Session `live-stage4-e2e-002` (26yo, Bengaluru, 0 dependents, no PED): `approved: True`, `escalation: False`, `escalation_reason: None`.

## In progress

- September 26 maintenance and fresh preflight/browser verification are complete and awaiting review. The full backend suite now passes in the existing Linux Docker image.
- `explanation_report` and `escalate` remain stubs. The graph still ends at `guardrail`; there is no functioning notification dispatcher or delivery hold. The current API still exposes draft/calculator data regardless of escalation. This is a release blocker, not a completed safety control.

## Known deviations from the docs (and why)

1. **Frontend modernized to Next.js App Router.** The legacy Vite+React prototype was retired. The frontend under `frontend/` is built on Next.js 16 (App Router) + Tailwind CSS v4, adhering to `PROJECT_STRUCTURE.md` and `docs/design.md`. Design tokens enforce Harbor (`#2C5F73`) as primary action color, Sky Blue (`#5BA9D8`) as secondary accent, two-tier Amber/Clay severity split, and IBM Plex font family with Devanagari multilingual readiness.
2. **`webhooks.py` created but deferred.** File exists for structural completeness; WhatsApp is Phase 4+ scope.
3. **`life_domain_agent.py` deferred & `life_deferred` routing branch.** `life_domain_agent.py` exists for structural completeness; life insurance is Phase 5 scope per the master roadmap. In Phase 1, `route_after_intent` routes `intent == 'life'` to `life_deferred` (ending the turn with an explicit Phase 1 health-only scope disclosure) rather than invoking `life_domain_agent`. Reflected in LLD § 7.2 node table.
4. **`email_hash` added to `users` table.** Added alongside `phone_hash` to support email-based authentication (magic link / OTP / email+password per design.md § 8.2). Reflected and documented in `docs/insurance-platform-tech-stack-hld-lld.md` § 7.4.
5. **Seeded `policy_terms` data and calculator heuristics use unverified benchmarks.**
   - The seed data for HDFC ERGO Optima Secure, Care Supreme, and Star Health Comprehensive in `app.db.seed` contains plausible benchmarks for scaffolding and testing only.
   - The calculator constants in `app.calculators.risk_profile` (14% annual healthcare inflation rate, ₹15L metro / ₹10L non-metro tertiary care thresholds) and `app.calculators.health_cover_sizing` are working actuarial heuristics.
   - `app.graph.nodes.risk_analysis` consumes these constants through `calculate_risk_profile`; they are not independently verified policy facts. The 36-month PED assumption and room-rent heuristics in that calculator are also unverified. Deterministic arithmetic does not validate its inputs, and a calculation date must not be presented as evidence of source verification.
   - **CRITICAL COMPLIANCE REQUIREMENT:** Both the policy terms (all limits, entry ages, waiting periods, exclusions, rate tables) and the calculator constants must be audited, verified against current insurer policy documents, and approved by a qualified actuary/underwriter before real users ever see calculations or recommendations derived from them (AGENTS.md rules 5 & 6).
   - **September 26 recheck:** Confirmed the 0.14 inflation rate and 1,500,000 INR metro threshold in `risk_profile.py`, which is called by `risk_analysis.py`. The same restriction applies to both calculator assumptions and seeded policy rows; README.md now states it explicitly. No insurer or actuarial verification was performed in this maintenance session.
6. **September 22 completion claims required correction.** NRI was missed, not deliberately removed from Phase 1. Its guardrail predicate existed by September 22, but successful intake extraction discarded `is_nri` because it accepted only required fields. September 25 fixes this in `needs_intake` and tests the handoff to the existing deterministic escalation predicate. Residency is still optional: absence of a declaration does not establish resident status. No schema or routing was changed.
7. **Frontend follows the supplied visual reference with explicit limits.** September 25 replaces the generic landing/comparison presentation with cream/sky surfaces, editorial serif headings, a three-step guide, paper case file, clause sheet, and policy evidence table. The exact supplied JPEG is reused through a CSS image viewport for the house artwork; it is only 453 × 680 pixels for the entire reference, so the enlarged house remains soft. DM Serif Display, IBM Plex Sans, IBM Plex Mono and Caveat are retained as visual approximations; exact font identity cannot be recovered from the JPEG. Serif section headings and the three-step landing guide intentionally supersede the earlier hero-only serif/five-step presentation. Health-only scope is retained rather than implementing the reference's life-insurance tab. Unsupported insurer figures, identifiers and verification badges were removed from the redesigned landing/comparison routes; unverified placeholders and explicit preview labeling take their place. This session does not connect the frontend to a completed advisory pipeline.
8. **Confidence is a completeness/compliance heuristic, not a validated probability.** September 26 reruns produce 0.46 for an incomplete profile, missing policy values and explicit conflicting-source flags, and 0.00 when provenance is removed. A complete consistent control yields 1.00; a complete case with conflict flags yields 0.88. September 26 maintenance preserves conflict flags through `compare_verify`, reads its actual `annual_premium_inr` field, removes empty-profile fallback credit, preserves missing declarations in the profile snapshot, and gives no city-completeness credit to `unknown`. Five regression cases exercise the actual Stage 3 to Stage 4 path and related scoring gaps. An explicitly empty profile now receives zero profile credit (overall 0.80 with otherwise complete terms/evidence), including when a stale complete snapshot exists. The weights and 0.70 threshold remain uncalibrated. Automatic contradiction detection is still unimplemented; a complete flagged-conflict case at 0.88 does not trigger the low-score rule by itself. These fixture results must not be presented as measured accuracy, retrieval agreement, or a production-validated escalation policy.

## Eval status

- **Eval suite**: 8/8 starter cases passing (100% passing across all 8 eval categories).
- **Historical unit suite**: September 22 recorded 79/79. This is not a fresh September 25 pass.
- **September 25 focused tests**: 9/9 NRI regression cases pass with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and explicit `-p pytest_asyncio.plugin` (avoids an unrelated auto-loaded plugin). Successful model extraction, omitted model field, negation, substring false positives and later residency corrections are covered.
- **September 25 scoring evidence**: `backend/venv/Scripts/python.exe -m eval.stage4_preflight` (run from backend) passes its assertions, calls the actual guardrail, and saves `artifacts/stage4-preflight.json`. It requires neither an LLM nor a database. Source material is synthetic and deliberately contradictory.
- **September 26 full backend verification**: 97/97 tests pass in the existing Linux `insuranceai-api:latest` image, with container networking disabled. Saved JUnit evidence in `artifacts/backend-tests.xml`. The Windows attempt was blocked by the installed `asyncpg` native DLL; Docker is now available, so no OS security policy or dependency binary was modified. One existing API unit test needed its Stage 3 database dependency mocked; it still executes the actual graph and now asserts the escalation response. This is unit/graph verification, not a live API/notification delivery claim.
- **Frontend**: ESLint and production build pass; browser preview runs at `http://localhost:3000`. Desktop (1280 × 900) and mobile (390 × 844) inspected, with no document-level horizontal overflow. Theme toggle, policy-detail selection, claim-check placeholder response, and comparison navigation exercised in the actual browser.
- **Actual browser screenshots**: `artifacts/01-landing-light.png`, `02-comparison-light.png`, `03-comparison-dark.png`, `04-landing-mobile.png`. These are captures of localhost, not generated mockups.
- **September 26 frontend verification**: ESLint and production build pass. Four fresh actual Edge captures of localhost:3000 are `artifacts/2026-09-26-01-landing-light.png`, `2026-09-26-02-comparison-light.png`, `2026-09-26-03-comparison-dark.png`, and `2026-09-26-04-landing-mobile.png`. Inspected all layouts; the mobile capture was retaken after awaiting image decoding. `artifacts/frontend-review.json` records URLs, capture times, viewport sizes, image dimensions, zero browser runtime errors, theme persistence, detail selection, and honest claim-check preview feedback. Reproduce with `scripts/capture_frontend.cjs` (README instructions).

## Next task — review first; one node per session

The September 22 promise to implement/wire both nodes together is superseded by the user's pacing instruction. `escalate` was always planned as a downstream delivery control after report generation (LLD § 7.3); it was not meant to be counted as implemented with Stage 4. Its current flag has no downstream action.

1. Pause here for review of the September 26 four findings, maintenance changes and fresh frontend screenshots. Stage 5 remains unstarted.
2. The evidence-projection, premium-field and empty-profile gaps are fixed, and the full suite passes in Linux Docker. Before production reliance, establish labeled calibration evidence and a reviewed policy for conflicting sources; automatic contradiction detection remains future work (deviation #8).
3. Next new-node session: implement and test `escalate` only (notification dispatch, failure handling, idempotency and delivery-hold contract), then pause for review. Flag any proposed schema/routing change before touching it, per AGENTS.md. Do not claim a live notification until an authorized destination and actual delivery are verified.
4. Following reviewed session: implement `explanation_report` only and connect it to the already implemented `escalate`. Reports must generate regardless of escalation; release depends on approval and the delivery gate. Review the API response path so draft/calculator fields cannot bypass the hold. Pause again after this node. No release to real users while deviation #5 remains unverified.

---

### Session log

**2026-09-20 — Claude Opus 4.6 (Thinking) —** Phase 0 scaffolding. Read all docs (AGENTS.md, PROGRESS.md, PROJECT_STRUCTURE.md, master roadmap, HLD/LLD, eval harness, architecture prompt, design.md). Created backend repository skeleton: docker-compose.yml, pyproject.toml, Dockerfile, alembic config + initial migration (8 tables), app module stubs, eval harness skeleton, and test directories. Validated docker-compose config. Frontend untouched.

**2026-09-21 — Gemini 3.8 Flash (High) —** Completed Phase 0 and started Phase 1:
1. Verified live containerization: `docker compose up -d --build` brought up `insurance-api`, `insurance-postgres`, `insurance-redis`, and `insurance-chroma`.
2. Applied database migrations live via `alembic upgrade head` and seeded database via `app.db.seed` (verified 3 policies, 3 terms, 1 user, 1 session, 1 audit entry in Postgres container).
3. Documented compliance requirement regarding unverified seed policy numbers in `PROGRESS.md` (Deviation #5).
4. Implemented and wired Node 1 (`intent_router`) with deterministic conditional edge `route_after_intent` (`health_flow`, `life_deferred`, `unclear_intent`).
5. Verified live requests against `http://localhost:8000/health`, `/v1/consent`, and multi-turn `/v1/message` conversations (intake missing fields loop, complete profile calculation, life disclosure, and unclear intent clarification).
6. Total test suite expanded to 21 unit tests and 8/8 eval cases (all 100% passing).
7. Resolved all IDE static type checking issues: parameterized LangGraph generics (`CompiledStateGraph[Any, Any, Any, Any]`, `StateGraph[Any, Any, Any, Any]`), updated `lifespan` to `AsyncGenerator[None]`, and added complete type annotations and casts across all unit test modules.

**2026-09-21 — Gemini 3.8 Flash (High) —** Stage 3 (`compare_verify`) implemented and verified:
1. Implemented `app.graph.nodes.compare_verify` with deterministic Hidden Clause Detector, Transparency Scorer (0–100), and premium rate-table lookup. All numbers from `policy_terms` DB, zero LLM invention (AGENTS.md rule 5). Every clause carries source + last_verified (rule 6). No ranking language in any user-facing output (rule 1).
2. Wired Stage 3 fan-in in `build_graph.py`: both Stage 2 branches → `compare_verify` → `END`.
3. Updated API response to surface `draft_output`, `hidden_clauses`, `transparency_scores`.
4. Patched existing integration tests (`test_graph_wiring`, `test_intent_router`, `test_stage2_fanout`) with `_make_empty_db_session()` mock to prevent asyncpg event-loop conflicts when graph now routes through Stage 3.
5. Total unit tests: 50/50 passing (added 26 Stage 3 tests). Eval suite: 8/8 passing.
6. Live end-to-end verified: session `live-stage3-e2e-001` — 3 turns, full pipeline intake → intent → Stage 2 fan-out → Stage 3 fan-in → API response with 3 policies evaluated, transparency scores, and high-severity PED clauses flagged.
1. Retired legacy static Vite prototype (verified purely Stitch-exported HTML with no state/logic).
2. Configured Tailwind CSS v4 design token system in `frontend/app/globals.css`:
   - Enforced Harbor (`#2C5F73`) as primary action/link color.
   - Enforced Sky Blue (`#5BA9D8`) as secondary accent.
   - Implemented two-tier severity split: Tier 1 Amber (`#B96A18`) for caveats/trade-offs, Tier 2 Clay (`#A44A2F`) for critical exclusions and room-rent deduction gaps.
   - Set up Moss (`#3F6B4A`) verified indicators and Paper (`#F8F3E9`) / Sky (`#EAF1F6`) atmospheric canvas registers.
3. Configured font hierarchy in `frontend/app/layout.tsx`: `IBM_Plex_Sans` for body/UI text (with Devanagari multilingual readiness), `DM_Serif_Display` strictly for hero headline, `IBM_Plex_Mono` for actuarial data, and `Caveat` for handwritten notes.
4. Updated UI primitives in `components/ui/` (`Button`, `Badge`, `StatusPill`, `Card`, `EvidenceLabel`, `ProgressPath`, `SectionContainer`).
5. Implemented marketing components in `components/marketing/` with the approved 5-step process flow in `ProcessSteps.tsx` (including Step 5: "Stay covered"), and Coverage Gap diorama with pinned Amber/Clay/Moss annotations in `HeroSection.tsx`.
6. Built and cross-checked the 5 product components in `components/product/` (`PolicyFactsPanel`, `ExhibitTag`, `ChainOfCustody`, `AgentClaimChecker`, `UINBadge`) against backend `/v1/message` response shapes (`citations`, `session_id`, `calculator_outputs`) and database models (`policy_terms`, `policy_documents`, `audit_log`).
7. Implemented route groups: `app/(marketing)/` (landing page, `how-it-works`) and `app/(product)/` (`sign-in`, `intake`, `comparison`, `handoff`).
8. Verified strict compliance with `AGENTS.md` Rule 1 (zero ranking/sales terms).
9. Successfully validated full production build with `npm run build` (all 9 routes compiled and prerendered cleanly, zero TypeScript errors).

**2026-09-21 — Gemini 3.8 Flash (High) —** Stage 4 (`guardrail`) implemented, tested, and verified live:
1. Implemented `app.graph.nodes.guardrail`:
   - AGENTS.md Rule 1: prohibits "best", "rank", "ranking", "top", "winner", "#1".
   - IRDAI Unlicensed Advice check: blocks promissory statements ("guaranteed return", "you must buy").
   - AGENTS.md Rule 6 Provenance verification: asserts source + last_verified across all policy terms, cited facts, and hidden clauses.
   - AGENTS.md Rule 5 Deterministic numeric sanity checks: min <= max, valid entry ages, non-negative waiting periods.
   - Confidence scoring: (0.0 to 1.0) feeds into Human Advisor Escalation rule.
   - Human Advisor Escalation: deterministic triggers for pre-existing conditions (PED), senior citizen applicants (60+), high sum insured (>= ₹1Cr), zero eligible policies, or low confidence (< 0.70).
   - AGENTS.md Rule 4 Contract: sets `approved`, `escalation`, `escalation_reason`, `guardrail_notes`; NEVER writes `output`.
2. Wired in `build_graph.py`: `compare_verify` → `guardrail` → `END`.
3. Updated `app.api.v1.message`: exposed `approved` and `guardrail_notes` in `MessageResponse` and API handler.
4. Added 27 unit tests in `tests/unit/test_stage4_guardrail.py`. Total test suite expanded to 77/77 passing unit tests (0 failures, 0 regressions).
5. Live verified in Docker container:
   - PED session `live-stage4-e2e-001`: `approved: True`, `escalation: True`, `escalation_reason` accurately citing pre-existing conditions.
   - Clean session `live-stage4-e2e-002`: `approved: True`, `escalation: False`, `escalation_reason: None`.

**2026-09-22 — Gemini 3.8 Flash (High) —** Resolved Stage 4 prerequisites prior to Stage 5:
1. **NRI Escalation Criteria**: Identified as missed from `guardrail.py` during Stage 4 implementation because NRI was not in `REQUIRED_HEALTH_FIELDS` in `needs_intake`. Added NRI detection to `evaluate_escalation()` in `guardrail.py` and keyword extraction in `needs_intake.py`.
2. **Discriminating Confidence Scoring**: Overhauled `calculate_confidence_score()` to evaluate policy term completeness (sum insured, entry age window, waiting period, premium estimate), retrieval evidence & conflicts, profile completeness, and compliance violations. Verified against a low-quality draft (missing policy fields, conflicting sources, incomplete profile) which now produces a score of **0.46** (below the 0.70 threshold, triggering escalation), resolving the previous cosmetic 0.85 score.
3. **Deviation #5 Expansion**: Updated `PROGRESS.md` Deviation #5 to explicitly cover calculator heuristics in `risk_profile.py` (14% annual medical inflation, ₹15L metro tertiary care threshold) alongside seeded `policy_terms` data as unverified benchmarks requiring actuarial audit before user launch.
4. **`escalate` Node Wiring Confirmation**: Formally confirmed that `escalate` is a delivery gate (not a generation gate) per AGENTS.md Rule 4 and LLD § 7.3. It will be wired immediately after `explanation_report` next session, holding `output` from the user response and notifying the advisor queue when `escalation == True`.
5. **Frontend Visual Verification**: Captured screenshots of the Next.js frontend across 4 routes (`/`, `/comparison`, `/how-it-works`, `/intake`), verifying design tokens, typography, and AGENTS.md Rule 1 compliance.
6. Total unit test suite expanded to 79/79 passing tests (`tests/unit/`).

**2026-09-25 — Codex — Pre-Stage-5 audit and supplied-reference frontend refresh**
1. Read AGENTS.md and PROGRESS.md first; verified implementation against the September 22 log rather than relying on its completion claims. No Stage 5 code, graph routing or schema was changed. No new graph node was implemented.
2. Fixed the remaining NRI omission in the existing `needs_intake` node: successful model JSON now accepts optional NRI/coverage fields; explicit declarations are retained when the model omits them. Deterministic fallback handles negation, word boundaries, and later corrections. Nine focused regression tests pass, including intake-to-escalation predicate behavior.
3. Added `backend/eval/stage4_preflight.py` and executed it. Actual sourced-but-incomplete guardrail case: **0.46**, `approved=true`, `escalation=true`, reason explicitly low confidence. Removing source metadata: **0.00**, `approved=false`, `escalation=true`. Formula controls: complete consistent **1.00**, complete conflicting **0.88**. Saved inputs and results in `artifacts/stage4-preflight.json`. Existing conflict flags are synthetic fixtures; upstream flag preservation and automatic contradiction detection remain unproven, explicitly logged in deviation #8.
4. Expanded deviation #5 with the exact `risk_analysis` → `risk_profile` dependency, 14% inflation, ₹15L/₹10L thresholds, and other unverified calculator assumptions. These require validation before user-visible recommendations.
5. Corrected the next-session plan: `escalate` is still a stub. The new-node sequence is escalate → review → explanation_report plus connection to the existing delivery gate → review. Generation remains unconditional with respect to escalation. Session pacing is now durable in AGENTS.md.
6. Rebuilt landing and comparison presentation from the supplied reference using the original house JPEG, editorial typography, blue/cream atmosphere, paper case file, clause card and evidence table. Added a persistent theme switch, responsive navigation, functioning detail selection and honest claim-check preview feedback. Updated shared headers/marketing footer. Replaced fabricated verification displays on those two routes with source/date-pending states. Other existing product routes are still prototypes.
7. Visually inspected desktop and mobile in the browser; fixed the intermediate-width hero wrapping. Captured four real localhost screenshots in `artifacts/`. Frontend lint/build passed. Full backend suite could not collect because a native dependency is blocked by Windows Application Control; Docker engine is unavailable. These are recorded as limitations, not passing checks.
8. Current stopping point: user review. Stage 5 has not started.

**2026-09-26 — Codex — Session instruction review**
1. **Built:** No implementation requested or added. Read AGENTS.md and PROGRESS.md and recorded the session requirements here.
2. **Deviations:** No implementation or architecture deviations. This session update is documentation only; no schema or routing changes were made.
3. **Validation:** Reviewed the existing progress record. No code tests were run for this documentation-only update.
4. **Next task:** Review the September 25 preflight findings and frontend changes. Stage 5 remains paused. After review, address the confidence evidence projection/calibration gaps and backend test-environment limitation in a bounded maintenance session; the next new-node session remains `escalate` alone, followed by user review.

**2026-09-26 — Codex — Pre-Stage-5 maintenance, fresh evidence and Git preparation**
1. **Built/fixed:** Read AGENTS.md and PROGRESS.md first. Reconfirmed NRI was missed, not removed from Phase 1. Repaired the additional `non-resident Indian` / `non resident Indian` negation collision, handled `not living abroad`, and respected explicit `is_nri=false` over a stale legacy `nri=true` value. NRI regression coverage is now 13 cases.
2. **Built/fixed:** Preserved existing conflict metadata in Stage 3; aligned confidence scoring with the producer's `annual_premium_inr`; removed empty-profile fallback credit and invented snapshot defaults. Added five producer/consumer regression cases. No database/state schema or graph edges were changed. No new graph node was implemented.
3. **Actual confidence results:** Sourced, incomplete, conflicting case = **0.46**, `escalation=true`; missing provenance = **0.00**, `approved=false`; complete consistent control = **1.00**; complete conflicting control = **0.88**. The actual Stage 3 to Stage 4 test also yields **0.46**. Saved fresh timestamped evidence in `artifacts/stage4-preflight.json`.
4. **Validation:** Full backend suite **97 passed** in network-isolated Linux Docker; frontend lint and production build passed. Four actual localhost screenshots captured and visually inspected at 1280 x 900 and 390 x 844. Browser theme persistence, detail selection and claim-check preview interactions passed, with no runtime errors or document-level horizontal overflow.
5. **Deviations and why:** This was bounded maintenance within existing nodes, not Stage 5 implementation. Windows native-library and sandbox helper failures required the existing Linux Docker image for tests and an isolated Playwright/Edge process for captures. The older API unit test depended on a live database; its database boundary is now mocked while the graph remains real. Confidence calibration, automatic contradiction detection and verification of policy/calculator sources remain unresolved release requirements, explicitly recorded in deviations #5 and #8.
6. **Git:** Initialized the root repository on `main` for the user-specified destination `https://github.com/mohdshubair313/Assurely.git`. Added README.md and root ignore rules for credentials, environments, dependencies, build output and local capture tooling. The publication payload includes source, documentation, tests and review evidence (181 files, including 55 frontend files). Preserved the pre-existing nested frontend Git history in ignored `.local/frontend-git-history` and staged its source as ordinary root-repository files; no submodule dependency is introduced. Credential-pattern scan found no matches in the source payload.
7. **Next task:** User review of this maintenance session. Then implement/test `escalate` alone (notification failure handling, idempotency, delivery hold), pause for review, and only in a following session implement `explanation_report` and connect the delivery gate. `escalate` was planned downstream of report generation; it was never implemented with Stage 4. Both nodes remain stubs and there is currently no notification or delivery-hold action.
