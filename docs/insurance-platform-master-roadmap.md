# Master roadmap — zero to production

This is the document that ties everything else together. Read this first; it tells you what to build in what order and which of the other files to open when.

---

## 0. Document map

| File | What it's for |
|---|---|
| `insurance-platform-tech-stack-hld-lld.md` | The system design: state schema, node list, Postgres schema, API surface, guardrails inventory, data architecture |
| `insurance-platform-eval-harness.md` | How you know it's working: decision provenance, eval categories, metrics, feedback validation, the rubric→DSPy improvement path |
| `insurance-architecture-v5-consolidated-prompt.md` | The diagram, frozen. Not touched again unless a real architecture change happens, not a naming tweak |
| This file | The build order, the revised scope, and the full tool list in one place |

---

## 1. Revised scope — narrower than the diagram implies

The diagram shows the full system's shape. Building the full shape on day one is the mistake both reviewers flagged. Actual v1 scope:

- **One input channel.** Start with a plain web chat interface, not WhatsApp. It's faster to build and debug — no Business API approval, no webhook infrastructure, instant iteration in a browser. Move to WhatsApp once the core loop works, since that's the channel your actual users will want, but it shouldn't be what you're debugging against on day 3.
- **One product type.** Health insurance only. Life insurance, and the Life Insurance Domain Agent, wait for v2.
- **Deferred to explicitly later phases:** multilingual generation, voice input, family/shared access, renewal reminders, existing-policy upload, the public transparency page. All good ideas, all still in the feature list, none of them block a working core.

---

## 2. Phase-by-phase build plan

### Phase 0 — Foundation (target: 1–2 weeks)
- `docker-compose` stack: FastAPI, Postgres, Redis, a vector DB (Chroma to start). Nothing agentic yet.
- The LLM fallback wrapper: Groq → Gemini Flash → OpenRouter free, with retries, wrapped in the rate-limit decorator (not a graph node — see the build guide's orchestration section).
- `audit_log`, `consent_records`, `decision_trace`, and `policy_terms` tables live, even empty.
- 5–10 starter eval cases from the harness doc's section 3, one script that runs them and prints pass/fail.
- Try deploying this skeleton once, even with nothing real behind it — confirms the container/deploy path works before you've built anything worth losing to a broken deploy.

### Phase 1 — The core loop, one product type, no polish (target: 3–4 weeks)
- `input_validate` → `needs_intake` (with the Missing Info Detector loop actually looping) → `intent_router` (hardcoded to health for now, but wired as a real conditional, not skipped) → `health_domain_agent` + `risk_analysis` in parallel → `compare_verify` reading `policy_terms` for anything deterministic, RAG only for clause wording → `guardrail` (sets `approved`/`escalation`, doesn't write output) → `explanation_report` (writes `output`).
- Ingest 3–4 real health policy documents by hand into `policy_terms` and the RAG store. Don't automate scraping yet.
- Run the growing eval set after every change. This is where "every bug becomes an eval case first" starts being a habit, not a plan.

### Phase 2 — Trust, safety, and observability wired in (target: 2–3 weeks)
- Consent capture, `escalate` with the delivery-hold logic, `persist_memory`.
- Langfuse wired in for tracing (see eval harness section 9).
- RAGAS or DeepEval running against the eval set for retrieval- and generation-layer metrics, not just pass/fail.
- The ingestion-screening step for anything scraped, before it reaches the RAG store.

### Phase 3 — Data architecture hardening (target: 2 weeks)
- Semantic caching in front of `needs_intake` and `compare_verify` (build guide, section 13).
- The rubric-based trace scoring pipeline from the eval harness, section 8 — every trace gets a `credibility_score`.
- Feedback Review & Validation step live, even if "review" just means you personally look at the queue at this stage.

### Phase 4 — Deploy for real, get real usage (target: ongoing from here)
- Move off `docker-compose` on your laptop to a real host (single VM is fine — no Kubernetes yet, per the trigger conditions in the build guide).
- Start the WhatsApp channel now that the core is stable.
- Every real user interaction becomes eval material through the validated-feedback pipeline.

### Phase 5 — Systematic improvement, scope expansion
- DSPy/GEPA prompt optimization against the rubric-scored dataset (eval harness, section 8) — this is where "the harness gets better from its own traces" actually happens.
- Add life insurance, the second product type, using the same pattern already proven for health.
- Add the deferred features from section 1, one at a time, each with its own eval cases before it ships.
- Kubernetes only if a real trigger from the build guide's scaling section shows up.

---

## 3. Full tools & frameworks reference

| Layer | Tool | Notes |
|---|---|---|
| Backend/API | FastAPI | Async, streams naturally, pairs with LangGraph |
| Orchestration | LangGraph | Deterministic conditional edges — see build guide's "one rule that matters more than the framework" |
| Prompt optimization | DSPy (GEPA optimizer) | Phase 5, once you have a scored dataset to optimize against |
| LLMs | Groq, Gemini Flash, OpenRouter free tier | Fallback chain, not a single hardcoded provider |
| Vector DB | Chroma (MVP) → pgvector or Qdrant if you outgrow it | |
| Relational DB | Postgres | Users, consent, audit, decision_trace, policy_terms |
| Object storage | S3-compatible / self-hosted MinIO | Raw PDFs and scraped pages |
| Cache | Redis (session) + semantic cache layer (vector similarity) | Session state is ephemeral; semantic cache targets repeated questions |
| RAG/generation eval | RAGAS or DeepEval | Split retrieval-layer and generation-layer metrics — don't hand-roll this |
| Observability | Langfuse (self-hosted) | Galileo as a later option — see eval harness section 9 for the Cisco-acquisition caveat |
| Automation/glue | n8n (self-hosted) | WhatsApp bridging, scheduled ingestion refresh, escalation notifications — never the reasoning core |
| Containerization | Docker Compose → single host → Kubernetes only on a real trigger | |

---

## 4. What "production-ready" actually means for this project

Not more boxes on the diagram. In order of what actually earns the label, per both reviews combined: a working core loop for one channel and one product type; a growing eval set that scores retrieval and generation separately; a decision-provenance record for every recommendation; a feedback loop that validates before it learns; real deployment in a container, even a simple one; and observability that tells you what's happening without you reading every trace by hand. Everything past that — the second product type, the second channel, DSPy-driven optimization, Kubernetes — is real, and it's next, not now.
