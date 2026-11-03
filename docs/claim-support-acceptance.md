# Report claim-support acceptance cases

Candidate contract, 2026-10-24. All examples are synthetic. The semantic labels
below are proposed review labels, not completed human validation or measured model
accuracy. Runtime audit version: `claim-support-v1-citation-hold` in
`backend/app/graph/claim_support.py`; semantic prompt text remains unchanged.

Distinct normalized evidence statements in one sentence's citation set now
produce a deterministic uncertain hold before any model call. This conservatively
includes compatible combined evidence; reconciliation is not validated. Identical
evidence statements are unaffected. See [ordered acceptance gates and candidate
rejection](backend-release-order.md). Historical SDK experiments test the prompt
directly; they do not incorporate this later runtime containment.

| Cited evidence | Candidate sentence | Expected handling |
| --- | --- | --- |
| Dental care is excluded. | Dental care is excluded. | Exact-evidence pass without another model call |
| Dental care is excluded. | The wording excludes dental care. | Semantic supported candidate |
| Dental care is excluded. | Dental care is covered. | Unsupported: reversed negation |
| Dental care is excluded. | Maternity care is excluded. | Unsupported: unrelated benefit |
| Dental care is excluded. | Dental care is excluded. All other treatments are covered. | Unsupported: added assertion |
| Synthetic Cedar excludes dental care. | Synthetic Maple excludes dental care. | Unsupported: changed policy identity |
| Surgery is covered only when medically necessary. | All surgery is covered. | Unsupported: omitted condition |
| The database record is active today; this does not establish personal coverage. | You are covered by this policy. | Unsupported: expanded scope |
| A waiting period may apply. | A waiting period always applies. | Unsupported: removed uncertainty |
| Structured terms: Waiting period for Synthetic Cedar: 90 days | Waiting period for Synthetic Cedar: 90 months | Deterministic rejection: numeric claim changed |
| Retrieved wording only: Waiting period: 90 days | Waiting period: 90 days | Deterministic rejection: no structured numeric authority |
| Evidence for a different sentence mentions maternity. This sentence cites dental exclusions only. | Maternity is covered. | Unsupported: cannot borrow another sentence's citations |

The runtime accepts an entire report only when every sentence passes. Unknown,
missing, duplicated, malformed, truncated or uncertain verifier results, provider
errors and the verification deadline all leave it undeliverable. It does not
release a partial report or automatically rewrite failed claims. The numeric
rule is intentionally conservative: digit-bearing output, recognized English
quantity words, duration ordinals and Unicode numeric characters must match a
complete structured claim, modulo whitespace. Even a faithful numeric paraphrase
is withheld. This finite detector does not claim complete linguistic quantity
coverage; model approval cannot authorize a detected numeric assertion. Exact evidence
matching establishes reproduction, not the truth or current authority of a source.

## Validation and next review

Unit tests exercise the contract using mocked verifier responses. They do not
demonstrate that a real model assigns these labels correctly. Before production
reliance, review candidate labels, broaden the set to realistic policy wording,
run the real verifier with a pinned provider/model and prompt, inspect false
acceptances and false rejections, and obtain human acceptance. Include adversarial
instructions in both evidence and candidate sentences. The generator and verifier
may use the same provider through the existing fallback chain, so their errors
are not assumed independent. Each fallback model needs validation too.

The existing eight-case rubric results predate this behavior and are not fresh
evidence for this release. Re-run that evaluation after support-check calibration.
The subsequent live experiments and inactive cloud rule are documented in
[claim-support-experiment-results.md](claim-support-experiment-results.md).
They do not establish production model accuracy or source approval.
