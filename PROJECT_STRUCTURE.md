# Project structure

Matches the LLD's node table and Postgres schema exactly — file names should never drift from the names already used in `docs/insurance-platform-tech-stack-hld-lld.md`. If a node gets renamed in code, rename it in the doc in the same commit, not after.

```
insurance-advisor/
├── docs/                               # already in place
│   ├── insurance-platform-master-roadmap.md
│   ├── insurance-platform-tech-stack-hld-lld.md
│   ├── insurance-platform-eval-harness.md
│   └── design.md
├── AGENTS.md
├── PROGRESS.md
├── CODE_REVIEW_CHECKLIST.md
├── docker-compose.yml
│
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── alembic/
│   │   ├── versions/
│   │   └── env.py
│   ├── app/
│   │   ├── main.py                     # FastAPI app, mounts routers
│   │   ├── core/
│   │   │   ├── config.py               # env vars, settings
│   │   │   ├── security.py             # auth, RBAC role checks
│   │   │   └── rate_limiter.py         # session + platform-wide budget
│   │   ├── api/v1/
│   │   │   ├── router.py
│   │   │   ├── message.py              # POST /v1/message
│   │   │   ├── consent.py              # POST /v1/consent
│   │   │   ├── sessions.py             # GET /v1/session/{id}
│   │   │   └── webhooks.py             # POST /v1/webhook/whatsapp
│   │   ├── graph/                      # the LangGraph itself — the heart of the system
│   │   │   ├── state.py                # SessionState (LLD 7.1)
│   │   │   ├── build_graph.py          # nodes + conditional edges, wired per LLD 7.3
│   │   │   └── nodes/                  # one file per node — matches LLD 7.2 exactly
│   │   │       ├── input_validate.py
│   │   │       ├── needs_intake.py
│   │   │       ├── intent_router.py
│   │   │       ├── life_domain_agent.py
│   │   │       ├── health_domain_agent.py
│   │   │       ├── risk_analysis.py
│   │   │       ├── compare_verify.py
│   │   │       ├── guardrail.py
│   │   │       ├── explanation_report.py
│   │   │       ├── escalate.py
│   │   │       └── persist_memory.py
│   │   ├── calculators/                # deterministic, zero-LLM
│   │   │   ├── human_life_value.py
│   │   │   └── health_cover_sizing.py
│   │   ├── rules_engine/               # policy_terms lookups — never LLM-invented numbers
│   │   │   ├── eligibility.py
│   │   │   ├── premium.py
│   │   │   └── exclusions.py
│   │   ├── llm/
│   │   │   ├── providers.py            # Groq / Gemini / OpenRouter clients
│   │   │   └── fallback_chain.py       # retry/fallback wrapper; rate limiter attaches here
│   │   ├── rag/
│   │   │   ├── ingestion.py
│   │   │   ├── ingestion_screening.py  # untrusted-content check, before the vector store
│   │   │   ├── vector_store.py
│   │   │   └── retriever.py
│   │   ├── guardrails/                 # shared checks, imported by nodes — not one big file,
│   │   │   ├── pii_scrub.py            # per AGENTS.md rule 3: guardrails are distributed
│   │   │   ├── injection_screen.py
│   │   │   ├── ranking_language_check.py
│   │   │   └── citation_validator.py
│   │   ├── models/
│   │   │   ├── db/                     # one file per table, LLD 7.4
│   │   │   │   ├── user.py
│   │   │   │   ├── consent_record.py
│   │   │   │   ├── session.py
│   │   │   │   ├── audit_log.py
│   │   │   │   ├── escalation.py
│   │   │   │   ├── policy_document.py
│   │   │   │   ├── policy_terms.py
│   │   │   │   └── decision_trace.py
│   │   │   └── schemas/                # Pydantic request/response models
│   │   ├── db/session.py
│   │   ├── cache/
│   │   │   ├── redis_client.py
│   │   │   └── semantic_cache.py
│   │   └── observability/tracing.py    # Langfuse
│   ├── eval/                           # sits beside app/, tests it, doesn't ship with it
│   │   ├── cases/                      # eval harness doc, section 3
│   │   ├── runner.py
│   │   └── rubric_scorer.py
│   └── tests/
│       ├── unit/
│       └── integration/
│
└── frontend/
    ├── package.json
    ├── next.config.js
    ├── tailwind.config.ts              # Ink/Sky/Paper/Harbor/Clay/Moss tokens live here, nowhere else
    ├── app/
    │   ├── (marketing)/
    │   │   ├── page.tsx                # landing
    │   │   ├── how-it-works/page.tsx
    │   │   └── layout.tsx              # Sky register
    │   ├── (product)/
    │   │   ├── sign-in/page.tsx
    │   │   ├── intake/page.tsx
    │   │   ├── comparison/page.tsx
    │   │   ├── handoff/page.tsx
    │   │   └── layout.tsx              # Paper register, auth-gated
    │   └── layout.tsx                  # root layout, light/dark theme provider
    ├── components/
    │   ├── ui/                         # Button, Badge, Card — design-system primitives
    │   ├── marketing/                  # HeroIllustration, ProcessSteps
    │   └── product/                    # the 5 differentiating components
    │       ├── PolicyFactsPanel.tsx
    │       ├── ExhibitTag.tsx
    │       ├── ChainOfCustody.tsx
    │       ├── AgentClaimChecker.tsx    # "what did they tell you?" widget
    │       └── UINBadge.tsx
    ├── lib/
    │   ├── api-client.ts
    │   └── theme.ts
    ├── styles/globals.css
    └── public/
```
