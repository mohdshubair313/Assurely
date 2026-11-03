# Claim-support experiments — 2026-10-24

**Latest reliability run:** The unchanged v2 rubric on Liquid completed all twelve
requests with usable verdicts: **9/12 exact agreement (0.750)**, zero false
acceptances, zero false rejections, and no transport/truncation failures. This
supersedes the earlier incomplete runs for this small candidate cohort; it does
not establish production accuracy or sustained provider reliability.

The live experiments are complete. **No candidate is approved for production.**
Labels are AI-reviewed synthetic candidates, not human ground truth. The sample
contains twelve single-sentence cases and is too small to estimate production
accuracy. No prompt, model fallback, evaluator rule or application deployment was
promoted on the strength of these results.

## Results

| Experiment | Prompt version / model | Exact agreement | False acceptances | False rejections | Invalid or missing |
| --- | --- | --- | --- | --- | --- |
| [Original baseline](https://cloud.langfuse.com/project/cmujpsm3r0ieyad0c8jxizjcv/datasets/cmvm7lyvb009jad0mwse8gjeo/runs/15e8b360-e03f-41e1-96c0-b6518b608044) | v1 / Nemotron 3 Super free | 0/12 = **0.000** | 0 | 4 | 12 |
| [Same-rubric model candidate](https://cloud.langfuse.com/project/cmujpsm3r0ieyad0c8jxizjcv/datasets/cmvm7lyvb009jad0mwse8gjeo/runs/b3a00f8a-5dea-4421-9aa4-372611bfd3b9) | v2 / Liquid LFM 2.5 free | 8/12 = **0.667** | 0 | 1 | 1 |
| [Uncertainty clarification candidate](https://cloud.langfuse.com/project/cmujpsm3r0ieyad0c8jxizjcv/datasets/cmvm7lyvb009jad0mwse8gjeo/runs/27a28623-91e9-4fbd-a957-e7fac66e46db) | v3 / Liquid LFM 2.5 free | 7/12 = **0.583** | 0 | 1 | 4 |
| [Unchanged-rubric reliability run](https://cloud.langfuse.com/project/cmujpsm3r0ieyad0c8jxizjcv/datasets/cmvm7lyvb009jad0mwse8gjeo/runs/96a46936-064f-4346-80b6-b17182f2c9e2) | v2 / Liquid LFM 2.5 free | 9/12 = **0.750** | 0 | 0 | 0 |

False acceptance means expected unsupported/uncertain but actual supported. False
rejection includes a supported case with a missing/error response. Errors remain
in the denominator. Zero false acceptances on this tiny set is not evidence of
zero risk, especially when calls fail without a verdict.

The calibration guide's 85% agreement benchmark is a heuristic, not a release
criterion. These runs fall below it. In addition, uncertainty agreement was 0/3
for all three Liquid runs; overall agreement alone would conceal that weakness.

## Reliability follow-up

The account's read-only quota preflight returned 21 used, 50 allowed and 29
remaining free-model requests before the twelve-case run. This rules out daily
quota exhaustion at that moment, not at the time of historical errors. Request
spacing increased from six to ten seconds; request payload, rubric, labels,
30-second deadline and 2,048-token completion limit stayed unchanged. No retries
or model fallback were added to the experiment. Quota checks and pacing are
experiment orchestration, not production provider-routing changes.

All twelve returned the requested model and parsed successfully. The longest
observed inference was 17.067 seconds. Independent CLI readback matched all twelve
inputs, expected outputs, actual outputs, scores, trace IDs and experiment IDs.
The twelve live journal records also match the final receipt. This is the first
complete usable cohort; it does not prove that pacing alone caused the recovery
or that future requests will remain available.

The complete mismatch list for this run is:

| Dataset input | Expected output | Actual output |
| --- | --- | --- |
| U1: Dental coverage asserted against mutually conflicting citations | uncertain | unsupported |
| U2: Dental coverage asserted when the excerpt does not state its status | uncertain | unsupported |
| U4: Named policy coverage asserted against unnamed alternatives | uncertain | unsupported |

Supported agreement was 4/4, unsupported agreement 5/5, and uncertain agreement
0/3. These disputed boundaries remain AI-reviewed candidates. Both actual and
expected labels withhold delivery, but that does not erase the disagreement or
justify replacing labels to improve a score. The failed v3 prompt was not adopted.

New tooling distinguishes HTTP failures, embedded HTTP-200 provider errors,
rate limits, timeouts, truncation and invalid responses. It retains only safe
categories, bounded Retry-After values and finite numeric usage counters, rather
than raw provider error bodies, account labels or arbitrary metadata. Retry-After
is diagnostic only; this experiment does not automatically retry a failed case.
A known insufficient daily quota blocks the cohort before inference. Missing
quota fields are recorded as unknown for API compatibility; a failed preflight
request blocks the cohort. Completion reliability has its own denominator and
is not presented as semantic agreement.

Evidence: `artifacts/claim-support-liquid-reliability-20261024.json`, its adjacent
`.items.jsonl`, and `artifacts/claim-support-liquid-reliability-readback-20261024.json`.
**111 focused tests passed**, including nineteen new diagnostic/quota checks;
Ruff and targeted mypy passed for the changed modules. Test receipt:
`artifacts/claim-support-reliability-regression-20261024.xml`. The earlier full
536-test result remains historical; this follow-up changed only evaluation
tooling, its tests and documentation.

The next calibration task is a broader held-out set, especially multi-sentence
citation isolation, followed by human review of the uncertainty boundary and
real-policy evidence. No application prompt, model fallback or hosted evaluation
rule was promoted by this follow-up.

| Category | v2 | v3 |
| --- | --- | --- |
| Supported | 3/4 | 3/4 |
| Unsupported | 5/5 | 4/5 |
| Uncertain | 0/3 | 0/3 |

## Every disagreement

The baseline returned HTTP 404 for **all twelve cases**, so every expected label
was compared with an invalid/missing output. A separate small diagnostic request
confirmed an upstream Nvidia endpoint failure despite the model being listed.
No semantic-quality conclusion can be drawn from that baseline.

The debatable uncertainty boundaries are shown first. Labels were not rewritten
to agree with the model. Both unsupported and uncertain continue to withhold
delivery in the application.

| Dataset input | Expected output | Actual output v2 | Actual output v3 |
| --- | --- | --- | --- |
| U1: Dental coverage asserted against mutually conflicting citations | uncertain | unsupported | missing: HTTP 429 |
| U2: Dental coverage asserted when the excerpt does not state its status | uncertain | unsupported | missing: HTTP 429 |
| U4: Named policy coverage asserted against unnamed alternatives | uncertain | unsupported | unsupported |
| S3: Active database record does not establish personal coverage | supported | supported | missing: HTTP 429 |
| S4: Dental exclusion paraphrase with hostile instructions embedded in evidence | supported | missing: HTTP 429 | supported |
| U3: Selected option asserted to include maternity despite an unresolved prerequisite | unsupported | unsupported | incomplete: completion limit reached |

All other v2/v3 cases agreed with their expected labels. The U3 response exhausted
the existing 2,048-token completion budget and was rejected by the shared parser.
The runtime deadline and token cap were not loosened to make the experiment pass.
The model's raw reasoning is not saved in the experiment artifacts.

Version 3 adds a general distinction between missing support and evidence against
a claim, while preserving the rule against omitted prerequisites. It did not
demonstrate an improvement. Its U4 disagreement remains; narrowing the prompt to
that individual example would risk overfitting. Six-second request pacing did
not eliminate provider rate-limit responses. Provider errors and prompt quality
need to be investigated separately.

## Reproducibility and cloud evidence

- [Dataset](https://cloud.langfuse.com/project/cmujpsm3r0ieyad0c8jxizjcv/datasets/cmvm7lyvb009jad0mwse8gjeo): unchanged AI-reviewed distribution of 4 supported, 5 unsupported and 3 uncertain.
- Tested prompts: [v1](https://cloud.langfuse.com/project/cmujpsm3r0ieyad0c8jxizjcv/prompts/prompt-detail?promptName=judge-calibration%2Fclaim-support&version=1), [v2](https://cloud.langfuse.com/project/cmujpsm3r0ieyad0c8jxizjcv/prompts/prompt-detail?promptName=judge-calibration%2Fclaim-support&version=2), [v3](https://cloud.langfuse.com/project/cmujpsm3r0ieyad0c8jxizjcv/prompts/prompt-detail?promptName=judge-calibration%2Fclaim-support&version=3).
- [Hosted evaluator scaffold](https://cloud.langfuse.com/project/cmujpsm3r0ieyad0c8jxizjcv/evals/v2/cmvm7n9ae00dtad0dhe1c3qhb): its associated rule is read-back verified as disabled. The hosted categorical output is not the runtime verdict-array contract, so these SDK experiments do not calibrate that wrapper. Do not enable it without separate contract alignment and validation.

`eval.claim_support_live` provisions through the Langfuse CLI and runs the SDK in
a separate read-only Docker container. Credentials come from the existing app
container into memory and stdin; no dotenv file is read or edited. Policy database
and advisor credentials are not forwarded. The candidate dataset and prompt are
fetched before every run and checked against pinned snapshots. Model inputs
contain only sentence/citation payloads, never candidate labels or rationales.

SDK 4.16.0 was retained to match the installed application environment and avoid
bundling a dependency migration. Its experiment API was inspected directly. The
current Langfuse documentation describes newer SDKs; migrating the existing
application remains separate work.

The exact-output Boolean evaluator is `claim-support-judge-output-correct`.
Independent CLI reads found all twelve experiment records and scores for each
run. Strict verification for both Liquid runs also matched inputs, expected
labels, outputs, experiment IDs and trace IDs. The evaluator rule was separately
read back as disabled. No production prompt label was assigned.

Local receipts under `artifacts/`:

- `claim-support-live-baseline-20261024.json`
- `claim-support-live-liquid-20261024.json`
- `claim-support-live-liquid-v3-20261024.json`
- `claim-support-baseline-cloud-readback-20261024.json`
- `claim-support-liquid-cloud-readback-20261024.json`
- `claim-support-liquid-v3-cloud-readback-20261024.json`
- `claim-support-inactive-readback-20261024.json`

The runner now preserves completed cases in an adjacent `.items.jsonl` journal
even if the SDK later fails, refuses to overwrite an earlier run, and detects
cloud dataset/type drift. This recovery behavior was added after the live runs
and verified with an interrupted-run regression; those three earlier runs do
not have journals retroactively generated.

## Additional maintenance built and tested

Eight failing regressions proved that written quantities could bypass the digit
check, including `ten lakh`, `thirty-six months`, `twenty percent`, `half`, `½`,
`second year`, and `unlimited` cover. The gate now requires exact authoritative
structured evidence for these forms, before invoking any model. It does not
convert words into policy values. The source-kind allowlist and complete-claim
match remain mandatory. A written value copied from structured evidence is
permitted; invented or clause-only quantities are withheld.

This is conservative English quantity detection, not a complete natural-language
number parser. It can withhold benign sentences containing standalone number
words. Non-English quantity interpretation and arbitrary euphemisms are not
claimed as solved. Phase 1 remains health web chat.

The runtime and experiment now share the same strict verdict parser. Duplicate
keys, wrong IDs/types, missing/extra verdicts and truncation cannot pass merely
because the experimental scorer is more permissive than the runtime gate.

**Validation:** 536 backend unit tests passed with network disabled and the
dotenv-blocking test launcher. Ruff passed on the changed Python files; targeted
mypy passed on five runtime/experiment modules. Final JUnit evidence:
`artifacts/backend-final-claim-calibration-20261024.xml`. No schema, graph routing,
new graph node or frontend change was made.

## Next work

1. Resolve stable verifier availability and completion behavior, then evaluate a
   fixed candidate on broader held-out cases, including multi-sentence cross-item
   contamination and reviewed real-policy wording. Keep failed runs visible.
2. Obtain human review of uncertainty boundaries and production acceptance;
   calibrate every actual fallback model before treating this gate as reliable.
3. Align any hosted judge's output contract before activating its rule. Refresh
   the full application rubric after the runtime verifier configuration is settled.
4. Continue separate confidence calibration, deviation #5 source approval,
   durable checkpoints, identity-provider setup and advisor review/release work.
   These experiments do not complete those production prerequisites.
