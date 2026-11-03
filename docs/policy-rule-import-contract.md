# Shared policy-rule and import contract

**Later 2026-11-02 implementation:** [Policy publication gate](policy-publication-gate.md)
documents migration 005, typed applicability/conditions, independent authenticated
publication, overlap/freshness enforcement and scoped deterministic lookups.
Unsupported rule families, real-candidate approval and the reviewed report adapter
remain pending. The proposals below are historical design context, not a claim
that every proposed rule family is now executable.

**2026-11-02 update:** Durable staging and authenticated representation-review APIs are now implemented, with isolated Postgres migration/restart validation. See [policy review workflow](policy-review-workflow.md). Production rule publication/import, conditional interpretation and qualified approval remain pending. The October 30 implementation/proposal distinction below is historical; staging does not activate customer policy terms.

Checkpoint: 2026-10-30. Scope: source normalization and import preparation for Care, HDFC and Star, within release priority 2. This is not a database import or a claim-cost engine.

## Schema flag and current implementation

The existing `backend/app/models/db/policy_terms.py` stores coverage min/max, integer entry ages, PED days, exclusions/premium JSON and a required effective date with nullable expiry. Existing readers include `compare_verify`, `policy_status`, `structured_conflicts` and the premium rules engine. Writing the reviewed candidates directly into those columns would lose discrete coverage gaps, calendar-month semantics, conditions and approval provenance. A null expiry currently participates in open-ended runtime validity; an unknown source expiry cannot safely be mapped to that behavior.

**Flagged before implementation:** propose additive, immutable versioned rule storage and a reviewed adapter. No SQLAlchemy model, Alembic migration, runtime lookup, graph state or routing has changed in this checkpoint. Database changes below remain design proposals. The new format is an offline draft schema only.

Implemented files:

- `backend/app/db/policy_rule_draft.py`: strict draft types, conservative normalization and a digest-bound, blocked import preview.
- `backend/tools/prepare_policy_import.py`: local-PDF CLI. It has no database connection, Settings import, network client, model call or approval option.
- `backend/tests/unit/test_policy_rule_draft.py`: representation, evidence-tampering, missing-data and approval-boundary regressions.

The existing source-review format and validator are reused without modification. All original proposed values, evidence references, source hashes/access dates, conditions and unresolved notes remain embedded in each draft. Source documents still need the separate ingestion controls before RAG use.

## Implemented draft boundary

| Input | Normalized proposal | Deliberately unresolved |
| --- | --- | --- |
| UIN / variant | Nonblank source text | Correct identity, variant applicability and schedule selection |
| Coverage options | Discrete positive integer paise values, INR | Eligibility, interpolation, policy/channel selection |
| Adult age bounds | Explicit finite age or explicit unbounded maximum | Age basis, member eligibility, conflicting sources |
| PED wait | Integer plus original `days` or `calendar_months` unit | Credits, continuity, selected overrides and date arithmetic |
| Source effective / expiry dates | A date marked `requires_applicability_review` | Product revision versus policy inception, renewal applicability, supersession and expiry meaning |
| Missing source value | `unavailable` with null value | Never default to zero, an empty exclusion list, no co-pay, infinity or unlimited validity |
| Unsupported representation | `needs_interpretation` with null value | Preserve original text; do not repair ambiguous amounts or infer structured rules from prose |

The recognized unbounded-age phrases are exactly `Lifelong` and `No maximum entry age limit`, and only for the maximum age field. This lexical mapping remains a proposal; it does not resolve Care's competing product-page age cap. Decimal money conversion is exact to paise; shorthand, grouped numbers, exponent notation, non-finite values, nonpositive coverage, duplicates and amounts requiring rounding are withheld for interpretation. Coverage arrays retain source order and gaps.

`build_draft(raw_package, source_bytes, as_of=...)` validates the actual PDF byte set before conversion. `assess_draft(raw_draft, source_bytes, as_of=...)` rechecks bytes, dates, unique JSON keys, original package digest and expected normalized fields before reporting blockers. It detects incompatible finite age bounds. It does **not** discover or resolve general semantic source conflicts; existing unresolved notes remain blocking review items.

All drafts and previews are pending human review with import/production flags false. Even a fully populated synthetic package with empty review notes cannot authorize import. Caller-supplied reviewer/approval properties are rejected. An import preview is diagnostics, not a security credential. Its digest binds the normalized payload, embedded source package, dates and normalizer version. Re-normalizing on another date creates another draft digest.

The current source-package digest uses the existing validator's deterministic Pydantic serialization. Reordering package arrays may change that digest; do not claim semantic canonicalization or cross-version equivalence. Future approvals must bind the exact frozen serialized draft and generator version. A normalizer-version change requires a new draft and review.

## Proposed persistence and identity contract

These additive entities are the next migration design, not tables created today:

| Proposed entity | Required responsibility |
| --- | --- |
| `policy_source_versions` | Immutable source bytes hash, acquisition record, document kind, UIN, source URL, page count and screening status. Preserve current `policy_documents` links for RAG. |
| `policy_rule_versions` | Insurer/product identity, UIN, variant, cover basis and selected-option scope; exact draft/source hashes, normalizer version and applicability record. One marketing name cannot identify a version. |
| `policy_rule_facts` | Typed value, unit, scope, conditions, evidence references and availability/review status. A missing fact and an explicit zero/none/unbounded fact are different states. |
| `policy_rule_conflicts` | Competing fact/source identities, disputed field/scope, unresolved issue, resolution evidence and authenticated resolver. No automatic universal document precedence. |
| `policy_rule_reviews` | Authenticated reviewer identity and authority, decision, reason, exact draft digest, server timestamp, verification freshness/recheck date, and revocation/supersession links. |
| `policy_import_batches` | Transactional import receipt, idempotency key bound to digest, frozen imported version IDs and audit outcome. |

Published versions are immutable. Corrections create a new reviewed version; revocation blocks future selection while preserving past audit references. Deleting a source must not cascade away provenance of a previously delivered report. Future retention/access rules need an explicit decision before migration constraints are finalized.

Applicability must distinguish product revision date, issue/renewal eligibility interval, individual policy period, source acquisition date and human verification date. Unknown end date is a distinct state, not a null that means unlimited validity. A reviewed no-declared-end state still needs freshness/recheck handling. End-date inclusivity and timezone boundaries must be explicitly recorded and tested by the future adapter; no date interval is executable in this draft format.

No customer schedule or family data is copied into public product facts. Future schedule overrides and saved simulations require ownership/consent controls. Those features are not introduced by this source contract.

## Conditional rule contract for subsequent implementation

The blueprint's F01/F02/F03/F12 requirements inform this design; their production features and F04 simulator are not implemented here.

Each future rule needs a stable rule ID, exact version identity, typed term/value, applicability scope, evidence links, reviewed conditions, overrides, dependencies, availability status and human-verification timestamp. An empty rule collection must distinguish reviewed absence from missing extraction.

Required rule-specific fields:

- **Co-payment:** exact rate or amount, contractual amount basis, applicable claim/expense/member groups, triggers, exemptions, cap, composition with other co-payments and rounding. Do not assume a universal gross-bill basis or additive composition.
- **Deductible:** exact money, per-claim versus policy-year basis, individual/shared-family bucket, eligible expenses, reset rule and interaction with other adjustments. Unknown usage/reset state prevents a definitive claim calculation.
- **Room and other limits:** eligible category/amount, affected expense groups, proportional-deduction exclusions, scope and optional-cover overrides. Room restrictions do not automatically reduce every line item.
- **Waiting periods:** source unit, onset event, continuity/portability credits, enhanced-coverage scope and optional modification. Calendar-month arithmetic needs explicit month-end/leap-day acceptance cases before execution.
- **Exclusions:** trigger, scope, exception and override links. Care's provider emergency wording needs reconciliation; archive-list membership alone is not a current eligibility verdict.
- **Tariffs:** complete declared zone/age/family/coverage/tenure/option coordinates, rating age basis, address-resolution rule, source cells, base/gross/tax basis, modifier order, precision/rounding and applicability. An illustrative or partial grid must not become a lookup table through interpolation.

Represent executable predicates with an allowlisted, typed condition grammar and explicit unknown results. No raw SQL, Python `eval`, model-generated expressions or LLM routing. Unrecognized conditions block the dependent operation. Declared rule order and override dependencies require cycle/dangling-reference validation. Raw source text remains evidence, not executable logic.

Future annual state uses an explicit policy-year interval and member/shared-bucket identity for deductible usage and remaining benefit balances. Facts about the product must be separate from a customer's changing claim ledger. Replay requires a frozen rule-set digest, engine version, inputs and prior balances. No balance store, reset behavior, ledger or formula was built today.

## Approval and import protocol to implement next

1. Revalidate the frozen draft against pinned bytes, acquisition provenance and source identity; complete source screening separately. Do not trust the CLI's output flags or a client-uploaded validation receipt.
2. Resolve variant/applicability, conditions, conflicts and every fact required by the intended capability. Define capability manifests explicitly; unavailable premium can block pricing without masquerading as a zero premium. Current previews withhold the whole import because no approved persistence service exists yet.
3. Create review decisions only under authenticated, authorized reviewer identity. Derive identity/time on the server; bind decisions to the exact content hash and scope. Reject expired, revoked, superseded or mismatched decisions. A boolean or typed reviewer name in JSON is never approval.
4. In one transaction, recheck the decision and conflicting/overlapping active version constraints under appropriate locking, insert immutable version/facts/evidence and write an audit/import receipt. Repeated requests for the same approved digest are idempotent; changed content with a reused idempotency key fails.
5. Publish only capability-complete, reviewed versions. The runtime adapter must require that publication state, scope, freshness and applicability; it must not fall back to unverified seed values when a reviewed lookup is unavailable.
6. Emit source and last-human-verified metadata through deterministic lookups. A lookup timestamp and a PDF acquisition timestamp must not be relabeled as human verification. Preserve the graph's report-generation versus delivery distinction.

The authentication, revocation, concurrency and transaction requirements above are **acceptance criteria for future code**, not checks implemented by this offline CLI.

## Real-package execution and acceptance

Executed against archived official PDF bytes on 2026-10-30:

| Candidate | Typed proposals | Unavailable fields | Import approved |
| --- | ---: | --- | --- |
| Care | 6 | Variant, expiry, exclusions, premium | No |
| HDFC | 6 | Effective date, expiry, exclusions, premium | No |
| Star | 5 | Variant, effective date, expiry, exclusions, premium | No |

Artifacts: `artifacts/care-rule-draft-20261030.json`, `artifacts/hdfc-rule-draft-20261030.json`, `artifacts/star-rule-draft-20261030.json`. Each includes the draft and a digest-bound import preview. Full conditional evidence and HDFC/Star extracted grids remain separate review artifacts; they were not promoted into executable rules.

Acceptance for this checkpoint: strict types preserve known representations; missing/unsupported values remain unavailable; dates do not silently activate policies; evidence and conditions survive; modified PDFs/drafts and false approvals fail; all three candidates produce blocked previews. **57 focused tests passed** across draft normalization (39) and existing source-review validation (18). This establishes representation/integrity behavior, not insurer approval or production readiness.

Targeted Ruff and mypy passed. Fresh PDF-backed readback reproduced all three saved previews and digests exactly. An attempted CLI write to the existing Care output failed with `FileExistsError` and preserved its hash. Evidence: `artifacts/policy-rule-contract-tests-20261030.xml` and `artifacts/policy-rule-contract-readback-20261030.json`.

Next: implement additive normalized persistence and authenticated review/import enforcement with a focused transaction/revocation/idempotency gate. Complete rule interpretation and calculator-assumption approval within release priority 2. Care full tariff sourcing remains an explicit external-data dependency. Broader auth/durable-state/advisor release work stays priority 3; frontend/API journey stays priority 4.
