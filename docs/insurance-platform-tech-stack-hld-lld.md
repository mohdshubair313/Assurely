# Insurance platform — tech stack, HLD & LLD

Practical build reference: what to actually use, what to skip, and how to structure the codebase to match the architecture diagram.

---

## 1. Free LLM providers — how to actually use them

| Provider | Free tier (verified mid-2026) | Best for | Watch out for |
|---|---|---|---|
| **Groq** | No card; ~30 RPM, ~14,400 requests/day shared across your keys; runs open models (Llama 3.3 70B, gpt-oss-120b, Whisper-large-v3) at 280–1,000 tokens/sec | The fast, cheap conversational turns — Needs Intake Q&A, quick classification/routing, and voice transcription for the WhatsApp/voice channel via Whisper | Open-source models only; weaker than frontier models on hard multi-step reasoning |
| **Google Gemini (AI Studio)** | No card; Flash and Flash-Lite class models only — Pro-class models moved to paid-only in April 2026; limits vary by model (roughly 10–30 RPM, up to 1M TPM on Flash-Lite) | Long-context reasoning — Compare & Verify and Guardrail agents that need to read a lot of retrieved policy text at once | Free-tier prompts may be used to improve Google's products — don't route unmasked health/PII data through it; enable billing once you're handling real user data even if you stay within free-tier cost |
| **OpenRouter** | One API key, ~20–28 rotating `:free` models (Llama, Gemma, Qwen, DeepSeek-class); 20 req/min always; 50/day unfunded or 1,000/day once you've ever added $10 in credits | Automatic fallback when Groq or Gemini rate-limits mid-session — this is literally the "retries + fallback" behavior your Orchestrator needs | Free model list rotates without much notice — call by capability with 2–3 fallback IDs, never hardcode one model |

**Recommended pattern:** wrap all three behind one internal `llm_call(task, ...)` interface with an ordered fallback chain (Groq → Gemini Flash → OpenRouter free) rather than hardcoding a provider anywhere in the agent code. Swap in paid models per-task once revenue allows — Compare & Verify and the Guardrail agent are the two most worth upgrading first, since they carry the most compliance weight.

---

## 2. Orchestration framework

- **LangGraph — use this as the core.** Reached its 1.0 release, MIT-licensed. It's built for exactly what this architecture needs: cyclic graphs (Missing Info loop, Needs Intake follow-ups), parallel node execution (the five-agent fan-out), built-in checkpointing (Audit trail), human-in-the-loop interrupts (Human Advisor Escalation), and session continuation. The separate, consent-gated User Profile Memory is stored as a structured Postgres JSONB snapshot, not in the LangGraph checkpoint or vector store. In 2026 production benchmarks it holds up best specifically on complex, multi-step, branching tasks — your exact category.
- **CrewAI — only for a throwaway first prototype.** Role-based, fastest to get a demo running if the team is new to agent frameworks. But it's weaker on cycles, checkpointing, and human-in-the-loop — the parts your compliance layer actually depends on. If you start here, plan to migrate the reasoning core to LangGraph before anything touches real user data.
- **Skip AutoGen.** Microsoft moved it to maintenance mode; its successor (Microsoft Agent Framework) is solid but pulls you toward the Azure ecosystem for no reason you need here.
- For a genuinely simple sub-agent (e.g., Risk Analysis — one model call plus a calculator tool), a lightweight SDK (OpenAI Agents SDK / Anthropic's Agent SDK) called as a single LangGraph node is often less code than forcing everything through the same heavy multi-agent abstraction.

**One rule that matters more than the framework choice.** Every routing decision in this graph — which domain agents fire, whether to escalate, whether to loop back for missing info — is a plain conditional edge over explicit state (`intent`, `escalation`, `missing_fields`), decided in code, not by asking an LLM "what should happen now?" That's the difference between a reliable state machine that calls LLMs for narrow reasoning tasks, and a "crew of agents" that gets unpredictable the moment two of them disagree. The design in this doc already works this way — write the rule down so it stays that way once other people touch the code.

---

## 3. Automation tools — n8n and Zapier, honestly

**Not for the agent brain.** n8n's AI Agent nodes are a visual wrapper around LangChain under the hood — great for chat, simple RAG, and tool calling without code, but not built for the custom retrieval pipelines, persistent memory, and fine-grained guardrails your Compliance layer needs. Zapier is further still from this use case — built for simple app-to-app triggers, not stateful multi-agent reasoning, and gets expensive fast at any real volume.

**Where n8n (self-hosted, free Community Edition) genuinely earns a place — the glue, not the brain:**
- Bridging WhatsApp Business API messages to your backend
- Scheduled refresh jobs for the Truth Layer (nightly pull of IRDAI ratio updates, insurer site diffs)
- Routing a Human Advisor Escalation event to an actual notification (Slack, email, CRM ticket)
- Shipping audit-log exports to durable storage

A pattern that works well in practice: n8n handles triggers and integrations, and your LangGraph graph runs as a separate service (or inside an n8n Code node) that n8n calls over HTTP for the actual reasoning. You get n8n's fast integration work without cramming compliance-critical logic into a canvas that's hard to unit-test or audit.

---

## 4. Full stack recommendation

| Layer | Choice | Why |
|---|---|---|
| Backend/API | FastAPI (Python) | Async, streams agent output naturally, pairs directly with LangGraph |
| Agent orchestration | LangGraph | See above |
| LLMs | Groq + Gemini Flash + OpenRouter (fallback chain) → paid models as revenue allows | Free-tier coverage without single-provider lock-in |
| Vector DB / RAG | Chroma for policy-clause retrieval in the current MVP; pgvector or another vector store is a future option | Semantic search over policy text, not User Profile Memory |
| Relational DB | Postgres | Structured User Profile Memory (JSONB), consent records, audit trail and policy terms; LangGraph also supports a Postgres checkpointer |
| Session/cache | Redis | Rate limiting, short-term conversation cache |
| Automation/glue | n8n (self-hosted) | WhatsApp bridging, scheduled data refresh, escalation notifications |
| Observability | LangSmith or Langfuse (open-source) | Tracing every agent step — doubles as your audit trail's technical backbone |
| Hosting | A provider with an India region (AWS ap-south-1, GCP asia-south1, Azure Central India) | Latency, and it simplifies the DPDP data-residency conversation with your compliance advisor |

---

## 5. Features to add beyond what's drawn

- **Multilingual output, not just multilingual input.** Multi-channel input covers WhatsApp/voice, but the actual explanation layer should reply in the user's own mix of Hindi/English, not just accept it.
- **An explicit intent router** before the domain agents fire, so you're not running (and paying for) a Life Insurance agent when someone only asked about health cover.
- **Renewal/lapse reminders** (phase 2) — once someone has a policy, a simple reminder before it lapses builds trust with very low compliance risk, since it's a reminder, not new advice.
- **A one-click "why am I seeing this" explainability view** on every recommendation — the direct product expression of your "no raaz" positioning.
- **A public, no-login "explainer" mode** (what's the difference between term and ULIP, generic education) separate from the logged-in mode that requires consent capture for personalized recommendations — lets people try the product before handing over health/income data.
- **A feedback signal after each session** feeding, with consent, both the User Profile Memory and an internal model-quality dashboard.

---

## 6. HLD — high-level design

| Layer | Responsibility | Tech | Maps to diagram |
|---|---|---|---|
| Presentation | Web, mobile, WhatsApp, voice input/output | Next.js / WhatsApp Business Cloud API / any STT-TTS pair | Entry band |
| API gateway | Input validation, auth, rate limiting | FastAPI + Redis | Input Validation, Rate Limiter |
| Orchestration | Session state, routing, retries/fallback, parallel fan-out | LangGraph | Orchestrator |
| Agent layer | Needs Intake, domain agents, Risk Analysis, Compare & Verify, Guardrail, Explanation & Report | LangGraph nodes, each calling the LLM fallback chain + relevant tools | Layer 1 boxes (Stages 1–5) |
| Data / RAG layer | Grounded retrieval over tiered sources | pgvector/Chroma + scheduled ingestion jobs | Layer 2a |
| Trust & Safety layer | Consent, audit log, escalation, disclosure | Postgres tables + n8n notification hooks | Layer 2b |
| Output layer | Final rendering with citations | FastAPI response schema → frontend components | Layer 3 |
| Observability | Tracing, cost tracking, audit export | LangSmith/Langfuse | Cross-cutting |

---

## 7. LLD — low-level design

### 7.1 LangGraph state (sketch)

```python
class SessionState(TypedDict):
    session_id: str
    user_profile: dict          # age, dependents, income, city_tier, health_flags...
    consent: dict                # what the user has agreed to, timestamped
    intent: str | None           # "life" | "health" | "unclear"
    missing_fields: list[str]
    calculator_outputs: dict     # human life value, ideal health cover, etc.
    retrieved_facts: list[dict]  # {claim, source, url, retrieved_at}
    hidden_clauses: list[dict]
    transparency_scores: dict
    draft_output: dict
    guardrail_notes: list[str]
    approved: bool                # set by guardrail; API delivery gate requires True
    escalation: bool
    escalation_reason: str | None
    delivery_hold: bool            # fail-closed API release gate; queue ACK never clears it
    advisor_notification: dict     # dispatch receipt; not advisor sign-off
    output: dict                  # written by explanation_report, not guardrail — see 7.2
```

### 7.2 Node list

| Node | Trigger | Reads | Writes | Calls |
|---|---|---|---|---|
| `input_validate` | new message | raw input | validated input | schema/PII checks |
| `needs_intake` | session start / missing_fields non-empty | user_profile | user_profile, missing_fields, calculator_outputs | LLM (Groq), calculator functions |
| `intent_router` | user_profile complete | user_profile | intent | LLM classification (cheap/fast model); routes to `health_flow`, `life_deferred` (Phase 1 scope disclosure), or `unclear_intent` |
| `life_domain_agent` | intent == "life" (Deferred: Phase 5) | user_profile | retrieved_facts (partial) | RAG retriever, LLM. *In Phase 1, `route_after_intent` directs `intent == "life"` to the `life_deferred` branch with scope disclosure instead of calling this agent.* |
| `health_domain_agent` | intent == "health" | user_profile | retrieved_facts (partial) | RAG retriever, LLM |
| `risk_analysis` | after intake | user_profile | calculator_outputs (risk-adjusted sizing) | calculator functions |
| `compare_verify` | after domain agents | retrieved_facts, `policy_terms` lookups | draft_output, hidden_clauses, transparency_scores | Deterministic rules-engine lookups for anything with a correct answer; LLM only for prose synthesis |
| `guardrail` | after compare_verify | draft_output | guardrail_notes, approved, escalation, escalation_reason | Hallucination check (re-query sources), rule engine — does **not** write `output` |
| `explanation_report` | after guardrail (runs regardless of escalation) | draft_output, guardrail_notes, retrieved_facts, target_language | output | LLM rendering call in target_language |
| `escalate` | after report generation; delivery hold applies if escalation or not approved | escalation_reason, output availability | advisor_notification receipt, delivery_hold | configured advisor queue; test receiver is not a production destination |
| `persist_memory` | every completed turn | full state, verified user identity when supplied, durable save_profile consent | unconditional `decision_trace`; consent-gated user profile snapshot | Postgres |

### 7.3 Request sequence

1. Message in → `input_validate` → rate-limit check.
2. `needs_intake` runs; loops on itself while `missing_fields` is non-empty.
3. `intent_router` sets `intent`.
4. LangGraph fans out in parallel to the relevant domain agent(s) + `risk_analysis` — plain conditional edges over `intent`, never an LLM deciding who to call.
5. `compare_verify` merges their outputs: deterministic lookups against `policy_terms` for anything with one correct answer (limits, exclusions, eligibility), RAG only for clause wording the response needs to explain.
6. `guardrail` fact-checks and enforces language rules; sets `approved` / `escalation` — it does not write the final text.
7. `explanation_report` always runs next, rendering the rationale, comparison, and citations into `output` — this gives an escalated case something concrete for the advisor to review, not a blocked draft.
8. `escalate` runs after report generation. It dispatches a notification when review is required and preserves delivery hold on escalation, missing approval, an unconfigured destination, or dispatch failure. A queue receipt is not advisor approval and never releases output. The API independently enforces this hold and redacts report/draft/calculator/citation fields while held.
9. `persist_memory` writes one decision trace on every completed turn, including early-return intake and intent routes. Only the separate profile-memory upsert is gated by verified user identity and active `save_profile` consent.
10. The API returns the result with per-claim source tags unless the escalation delivery hold applies.

### 7.4 Postgres schema (sketch)

```
users(id, phone_hash, email_hash, role, tenant_id, created_at)
    -- role: customer | advisor | admin
    -- tenant_id: nullable for now, reserved for future white-label broker partners
    -- email_hash: added for email-based auth (magic link / email+password per design.md § 8.2)
consent_records(id, user_id, scope, granted_at, revoked_at)
user_profile_memory(user_id, profile_snapshot_json, updated_at)
    -- profile_snapshot_json is JSONB: one structured, deletable family profile per user;
    -- written/read only with verified identity and active save_profile consent
sessions(id, user_id, started_at, ended_at, intent)
audit_log(id, session_id, node_name, input_hash, output_hash, sources_json, created_at)
escalations(id, session_id, reason, status, assigned_advisor, created_at)
policy_documents(id, insurer, product_name, doc_url, ingested_at, version_hash)

policy_terms(id, policy_document_id, version_hash, sum_insured_min, sum_insured_max,
             entry_age_min, entry_age_max, waiting_period_days_preexisting,
             exclusions_json, premium_rate_table_json, effective_date, expiry_date)
    -- structured, versioned, queried deterministically — never inferred by an LLM.
    -- RAG stays reserved for clause wording and explanations, not numbers or eligibility.

decision_trace(id, session_id, user_profile_snapshot_json, policy_versions_evaluated_json,
               clauses_retrieved_json, rules_engine_output_json, sources_per_claim_json,
               model_version, prompt_version, confidence_score, confidence_inputs_json,
               created_at)
    -- one row per recommendation. Answers "why did it say that" without reconstructing
    -- it from logs, and lets you replay the same input after a deploy and diff the trace.
```

**Identity/security boundary:** Profile-memory access requires a Bearer JWT verified against an HTTPS JWKS with RS256, a UUID `sub`, and valid `iss`, `aud`, `iat` and `exp` claims. The server requires `AUTH_ISSUER`, `AUTH_AUDIENCE` and `AUTH_JWKS_URL`; if issuer configuration or token verification is unavailable, identity-sensitive access fails closed. The API does not mint tokens, and no real identity provider is configured yet. An anonymous `/v1/message` turn without `user_id` can still write its unconditional decision trace. A message that supplies `user_id` must authenticate and match the token subject. Consent grants/revocations and profile-memory deletion likewise require a verified subject matching the requested user ID. Revoking `save_profile` or calling the deletion endpoint erases that user's stored snapshot.

**Decision-trace classification:** traces are currently treated as operational/compliance evidence and are retained regardless of profile-memory consent. This classification requires an actual review with the DPDP compliance adviser; it has not been approved yet. Langfuse content redaction does not redact Postgres decision traces.

### 7.5 API surface (sketch)

```
POST /v1/message        -> {session_id, user_id?, reply, citations[], escalation?}; Bearer identity required when user_id is supplied
POST /v1/consent        -> persist grant/revoke scopes only for verified token subject
DELETE /v1/profile-memory/{user_id} -> erase the verified token subject's stored profile snapshot
GET  /v1/session/{id}   -> full transcript + citations (for the audit trail / "why am I seeing this")
POST /v1/webhook/whatsapp -> inbound channel bridge (via n8n or direct Meta webhook)
```

### 7.6 Deployment topology

Containers: `api` (FastAPI) · `agent-runtime` (LangGraph, can colocate with api initially) · `postgres` · `redis` · `vector-db` · `n8n`. Start as a single docker-compose stack; split `agent-runtime` into its own scalable service once traffic justifies it.

---

## 8. Suggested build order

- **Phase 0 (this week):** stand up FastAPI + Postgres + Redis skeleton; wire the Groq→Gemini→OpenRouter fallback chain behind one function; get a single LangGraph node (Needs Intake only) talking to it.
- **Phase 1 (MVP, 2–4 weeks):** full LangGraph graph for one product type (health insurance only); 3–4 hardcoded authoritative sources ingested into pgvector; manual citation formatting; no purchase links yet.
- **Phase 2:** add Guardrail + Hallucination Guard, tiered truth layer, intent router, calculators, missing-info loop, WhatsApp channel via n8n.
- **Phase 3:** add Trust & Safety layer in full (consent UI, audit export, human escalation queue), expand to life insurance, add multilingual output generation, evaluate Bima Sugam integration once its APIs are public.

---

## 9. v3 alignment notes

The v3 diagram tightened three things worth carrying into the code exactly as drawn. Everything else in this doc — state schema fields, the rest of the node list, the stack table, the Postgres schema, the API surface, the deployment topology, the phased build order — stays as written above, since section 7.2's node table already assumed an `intent_router` and a sequential `compare_verify` step.

**Stage 2 as a real fan-out/join, not three independent edges.** `intent_router` dispatches to whichever of `life_domain_agent` / `health_domain_agent` / `risk_analysis` apply (LangGraph's `Send` API is the clean way to do this). `compare_verify` must wait for *all* dispatched branches to report back — a join, not a race where the first branch back triggers it.

**Rate Limiter is a wrapper, not a node.** It has to gate every one of the four stages' LLM calls for the whole session, so model it as a decorator/middleware around the shared `llm_call()` fallback function from section 1, keyed by `session_id` — not as its own step in the graph. A graph node implies "runs once, in turn"; that's the wrong shape for something that has to run on every call.

**Add `target_language` to the state schema:**

```python
target_language: str  # detected on first turn: "hi", "en", or "hi-en-mixed"
```

Detect it once during `input_validate` or the first `needs_intake` turn, and pass it through so whatever renders the final reply (inside or just after `guardrail`) generates in that language, rather than only accepting it as input.

---

## 10. v5 alignment notes — the `explanation_report` node

The v5 diagram added Stage 5 (Explanation & Report Agent) as its own step after Guardrail. Guardrail only approves (`approved`, `escalation`, `escalation_reason`); it does not write `output`. `explanation_report` must run unconditionally before `escalate`, so an escalated case gives the human advisor a report to review. `escalate` gates *delivery*, not *generation*. State includes `approved`, `delivery_hold`, and an `advisor_notification` receipt. The production advisor destination is unconfigured; a local loopback receiver is test infrastructure only. Current implementation is interim and fail-closed while `explanation_report` awaits review.

---

## 11. External review incorporated (AI engineer feedback)

A friend working as an AI applied engineer reviewed the v5 diagram. Their feedback sharpened rather than contradicted this document, and it's reflected above:

1. **Don't over-agent it.** Routing stays deterministic; LLMs are called only inside nodes that genuinely need reasoning. See the callout in section 2.
2. **Move eligibility, exclusions, limits, and dates into structured/versioned data, not RAG.** Now the `policy_terms` table in section 7.4, reflected in `compare_verify`'s row in the node table.
3. **Build the eval dataset and harness alongside development, not after** — and make it answer, for every decision: what user info, which policy version, which clauses, what the rules engine calculated, which sources, why that confidence level, which model/prompt version. This is big enough to warrant its own document: see `insurance-platform-eval-harness.md`.

---

## 12. Guardrails are distributed, not a single stage (engineer feedback)

Calling Stage 4 "the Guardrail Agent" implies guardrails live in one place. They don't — they're already spread across the system, and it's worth naming that explicitly rather than letting one box carry the whole concept:

| Guardrail | Where it lives | What it catches |
|---|---|---|
| Input validation / injection screening | Entry | Malicious or malformed user input |
| Rate limiter / cost control | Layer 1, attached to Orchestrator | Runaway spend, abuse |
| Ingestion screening | Layer 2b | Poisoned scraped content / indirect prompt injection |
| **Stage 4 — Compliance & Disclosure Agent** (renamed from "Guardrail Agent") | Layer 1 | Unlicensed-advice language, missing disclosures, unsupported claims |
| Human advisor escalation | Layer 1 | High-stakes or low-confidence cases an automated system shouldn't finalize alone |

Stage 4's job is specifically compliance and disclosure enforcement — worth the more precise name next time the diagram is touched for another reason. Not worth a dedicated regeneration round on its own.

---

## 13. Data architecture — storage & caching

| Data | Where it lives | Why |
|---|---|---|
| Session state (in-flight conversation) | Redis, TTL-based | Ephemeral, high read/write, doesn't need durability |
| User Profile Memory | Postgres `user_profile_memory.profile_snapshot_json` (JSONB) | Exact keyed reuse of age, city, dependents and health declarations, plus consent-gated reads/writes and row deletion; semantic embeddings are unnecessary for this record |
| Consent, audit log, decision_trace, policy_terms | Postgres | Durable, relational, needs to survive restarts and support queries |
| Raw ingested documents (PDFs, scraped pages) | Object storage (S3-compatible — AWS S3, or a self-hosted MinIO to start) | Large binary blobs don't belong in Postgres rows |
| Policy chunks for retrieval | Chroma in the current MVP; pgvector is an alternative | Vector similarity search over policy wording and explanations only |

**Implemented storage decision:** The earlier pgvector proposal for User Profile Memory was replaced with a Postgres JSONB snapshot. Profile fields must be read by exact key and erased on consent revocation or direct deletion; embedding sensitive family details would add no retrieval benefit. The vector store remains dedicated to policy-clause RAG. This is an intentional implementation choice, not an omitted vector-memory feature.

**Semantic caching is worth adding early, not as a later optimization.** A meaningful share of insurance questions repeat across users in different words ("does this cover critical illness" vs. "is critical illness included") — semantic caching catches these by comparing embeddings instead of exact text and serves a cached answer instead of a fresh LLM call. Production deployments of this pattern report cost reductions in the 40–86% range depending on query repetition, with cache hits returning in single-digit milliseconds instead of seconds. Practically: use your existing vector DB to store a cache of (query embedding → response), check it before every LLM call in `needs_intake` and `compare_verify` specifically (the two nodes handling the most repetitive question types), and only skip the cache for anything touching a specific user's private profile data, where a cached answer from someone else would be wrong by definition.

**Deployment scaling path.** Start with `docker-compose` on a single host — everything in this stack (FastAPI, Postgres, Redis, vector DB, n8n) runs fine there through real early usage. Move to Kubernetes only when a concrete trigger shows up: you need to scale the API/agent-runtime service independently of the database, you need zero-downtime deploys, or you have more than one environment (staging + prod) to keep consistent. Don't reach for K8s before one of those is true — it adds real operational overhead for no benefit at low traffic, and this architecture doesn't need GPU scheduling since every model call goes to an external API, not a self-hosted model.

**Diagram status, still: no further changes needed.** Everything in sections 12–13 is a documentation and schema change, not a reason to touch Eraser again. See `insurance-platform-master-roadmap.md` for how all of this fits into an actual build sequence.
