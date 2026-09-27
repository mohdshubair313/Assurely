# Assurely

An India-focused health insurance advisory prototype with a Next.js web interface
and a FastAPI/LangGraph backend. Comparisons use need-fit framing, deterministic
policy lookups, and source-linked explanations.

Read [AGENTS.md](AGENTS.md) and [PROGRESS.md](PROGRESS.md) before making changes.
Architecture and build order are in [docs](docs/).

## Current scope and release status

Phase 1 covers web chat and health insurance. The current interim graph is
`guardrail` → `escalate` → END. `explanation_report` remains a stub pending user
review. Escalation notifies only a configured receiver and independently holds
public delivery; the API suppresses report/draft/calculator details while held.
The frontend is a design preview, and other product routes remain prototypes.

Seeded policy terms and calculator inputs are **unverified scaffolding**. This
includes 14% annual medical inflation, the INR 15 lakh metro / INR 10 lakh
non-metro tertiary-care thresholds, waiting-period assumptions, and room-rent
heuristics. Both policy data and calculator assumptions need source verification
and qualified review before real users see derived recommendations. A calculation
timestamp is not evidence of source verification. See deviation #5 in PROGRESS.md.

Confidence is a completeness/compliance heuristic, not a calibrated probability.
Explicit conflict flags are retained through Stage 3; this does not establish
automatic contradiction detection or verified retrieval agreement.

Stage 5 is paused pending review of `escalate`. The local test receiver proves
HTTP queueing and delivery hold only; the real advisor-queue destination is a
Phase 2 task. After review, implement `explanation_report` in a separate session
and run it unconditionally before `escalate`.
Report generation must run regardless of escalation; delivery requires the gate.

## Local frontend

Requires Node.js and npm.

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:3000. Run `npm run lint` and `npm run build` in `frontend`
for static checks. These do not replace visual inspection.

## Local backend

Requires Docker with the Linux engine running.

```sh
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python -m app.db.seed
```

The Compose configuration uses local development credentials only. Keep real API
keys and deployment credentials in environment variables or an ignored `.env`.
Provider keys are optional for deterministic tests; live model calls require them.

## Verification

Run from the repository root after building the `insuranceai-api` image:

```sh
docker run --rm --network none --mount type=bind,source="<absolute project path>",target=/workspace --workdir /workspace/backend --env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 insuranceai-api:latest python -m pytest -p pytest_asyncio.plugin tests -q
docker run --rm --network none --mount type=bind,source="<absolute project path>",target=/workspace --workdir /workspace/backend insuranceai-api:latest python -m eval.stage4_preflight
```

The preflight saves its synthetic inputs, actual guardrail results, and execution
time to [artifacts/stage4-preflight.json](artifacts/stage4-preflight.json).

For actual browser screenshots with Microsoft Edge installed and localhost:3000
running:

```sh
npm install --prefix .local/browser --no-save playwright
node scripts/capture_frontend.cjs
```

Captures and the browser-check manifest are saved in `artifacts/`. `.local/`,
environments, credentials, dependencies, and build output are excluded from Git.
