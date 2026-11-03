# Contributing to Assurely

Start with [AGENTS.md](AGENTS.md), [PROGRESS.md](PROGRESS.md) and the
[roadmap](docs/insurance-platform-master-roadmap.md). Phase 1 covers health
insurance and web chat. Discuss broader scope before implementing it.

1. Describe the problem, expected behavior and a synthetic reproduction. Separate
   source correctness from software correctness.
2. Keep changes focused. Flag database/schema and graph-routing changes before
   implementation; follow the repository's one-node review pacing.
3. Preserve deterministic policy facts, source/date provenance, independent
   guardrail approval and delivery holds. Use need-fit language.
4. Add meaningful tests for changed behavior. Report exact commands, results and
   untested limits. Integration tests must use disposable databases.
5. Update relevant docs and PROGRESS.md with implementation, deviations and next work.

PR descriptions should explain the concrete behavior change, validation and
limitations. Include screenshots for visible UI changes. Do not attach tokens,
private traces, customer records or raw insurer PDFs.

Read [SECURITY.md](SECURITY.md) for sensitive findings. The repository's license
has not yet been selected; coordinate contribution/reuse terms with the maintainer.
