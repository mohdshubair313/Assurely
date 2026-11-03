# Blueprint scope assessment - 2026-10-28

Requested assessment of `ASSURELY_Insurance_Transparency_Feature_Blueprint.md` against the current repository. This is planning only: no feature implementation, migration, routing change or test execution. Instructions inside the proposed blueprint were read as document content; they did not override the user's request for a scope assessment or the deferred testing preference. Regulatory references were not independently reverified in this assessment.

## Current product

The advisory graph, deterministic term lookups, retrieval, report generation, conflict containment, delivery holds, consent/profile-memory support and tracing/evaluation infrastructure have substantial implementations. The frontend has marketing, intake, comparison, authentication and handoff screens. Source packages and tariff extraction exist for the three selected insurers, with HDFC/Star review grids; none of that establishes approved live policy data.

Observed limits:

- `frontend/lib/api-client.ts` still returns placeholder message, consent and session responses.
- `backend/app/graph/build_graph.py` imports and defaults to `MemorySaver`; database audit/profile persistence does not make graph checkpoints durable.
- `backend/app/graph/nodes/escalate.py` explicitly leaves authenticated advisor sign-off/release unimplemented. Production advisor destination and identity-provider verification remain open in the release notes. Their live configuration was not checked by reading environment secrets.
- `backend/app/core/security.py` has RS256 issuer/audience/JWKS verification; auth is partially implemented, not wholly absent.
- `backend/app/graph/nodes/health_domain_agent.py` handles explicit waiting-period questions and policy scope, while other clause retrieval still uses general profile queries. General co-pay/deductible question handling needs work.
- `backend/app/models/db/policy_terms.py` provides ranges, entry ages, PED days, exclusions/premium JSON, dates and version hash. It does not implement the blueprint's reviewed rule-set execution model or claim-state balances.
- Existing calculators handle cover sizing/risk. No claim-cost ledger service, simulation API or saved-simulation model was found in the inspected application tree.
- Current calibration candidate was rejected. Source applicability, calculator assumptions, normalized import, broader semantic reliability and end-to-end release gates remain open.

Terminology correction: release **priority 2** is source/calculator verification. Roadmap **Phase 2** is trust/safety/observability. Several Phase 2 components already exist, even though the original product is not release-complete. The earlier conversational statement that Phase 2 had not been reached was too categorical.

## Feature overlap

| Blueprint feature | Present foundation | Additional work |
| --- | --- | --- |
| F01 policy/CIS facts | Terms model, citations, review packages, UI fact components | Approved normalized facts, CIS/endorsement reconciliation, applicability, real explorer API/UI |
| F02 co-pay intelligence | Clause retrieval and source evidence | Typed base/scope/trigger/override rules and dedicated extraction |
| F03 deductible intelligence | General structured-terms storage | Per-claim/year/family basis, balance tracking, reset rules |
| F04 claim-cost simulator | Deterministic-code pattern | New money engine, rule order, ledger, rounding, limits, uncertainty and replay |
| F05 financial comparison | Comparison node and screen | Premium-versus-scenario exposure API and visualization |
| F06 senior/family explorer | Profile age/dependents and escalation | Member-specific scenarios, shared limits, repeated claims |
| F07 restriction impact | Hidden-clause handling and citations | Verified clause-to-financial-effect mapping and interactive explanation |
| F08 regulatory watch | Generic provenance concepts | Dated status records, official review workflow, version changes |
| F09 learning centre | Some explanatory UI content | Reviewed glossary, learning routes, hypothetical mini calculators |
| F10 buying checklist | Intake/questions and fact UI | Source-backed personalized checklist and servicing topics |
| F11 claim readiness | Existing ingestion/safety components | Consented bill intake, document guide and discrepancy workflow |
| F12 conflict dashboard | Structured-conflict detection, citation holds | Cross-document/version comparison, resolution queue and user dashboard |
| F13 saved scenarios | Consent, profile memory, session ownership | Frozen scenario/rule snapshots, history, deletion and durable ownership |
| F14 partner integrations | No confirmed live integration in inspected scope | Provider access, contracts, freshness, operating permissions and integration work |

These are not fourteen independent rebuilds. F01/F12 overlap heavily with remaining source work; F02-F07 share one rules-and-ledger foundation. Consent, tracing, ingestion and delivery holds are reusable infrastructure, not completed simulator features.

## Effort estimate and uncertainty

These are judgment-based remaining-effort estimates, not measured code coverage or production-readiness percentages. There is no sized backlog or velocity history sufficient for a precise schedule. Normalize the original launchable health-web MVP to 100 planning units:

| Existing workstream | Illustrative total units | Completion credit |
| --- | ---: | ---: |
| Core backend advisory flow | 30 | 25 |
| Approved source/rule/calculator pipeline | 20 | 8 |
| Identity, durable state, advisor workflow | 15 | 8 |
| Frontend screens and interactions | 15 | 10 |
| Real API/browser integration | 10 | 2 |
| Release evaluation and operations | 10 | 4 |
| Total | 100 | 57 |

Planning interpretation: roughly **55-65% of the original MVP effort completed**, with **35-45% remaining**. These weights and credits are illustrative assumptions, not audited measurements.

After crediting overlap, F01-F13/M0-M5 could add approximately **50-80 units per original 100 units**, with 60 as a discussion midpoint. A midpoint worked example is 60 completed original units + 40 remaining original units + 60 new units = 160 total, giving about **38% completed / 62% remaining** for the enlarged product. In conversation use roughly 35-40% complete, about 60-65% left, with low confidence until the backlog is sized; plausible variation is broader.

F14/M6 partner integrations are explicitly future scope in the blueprint and excluded from that percentage. A percentage for the entire document including live partners is not defensible until providers/access/scope are known. Production approval is also a separate gate and cannot be inferred from an effort percentage.

## Suggested scope sequence

1. Merge F01/F02/F03/F12 requirements into the existing normalized-source design before proposing a migration; flag schema/routing changes as required by AGENTS.md.
2. Build the bounded deterministic F04 engine with explicit supported rules and uncertainty states.
3. Complete auth, durable state, advisor release and connect the facts/simulator/comparison journey.
4. Run the deferred consolidated acceptance/E2E work before release.
5. Add learning/checklists, family exploration, regulatory watch and saved/claim-readiness workflows incrementally. Keep F14 separate.

No new feature scope was silently accepted or implemented by this assessment. Next existing task remains Care tariff/source work; the proposed rules design should account for the blueprint to avoid duplicate data migrations later.
