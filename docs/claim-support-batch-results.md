# Multi-sentence claim-support calibration — 2026-10-24

The fixed candidate failed this broader exploratory check. One sentence with conflicting evidence was incorrectly accepted. No runtime prompt/model change or production approval followed.

Eight synthetic batches contain 18 sentences: 10 supported, six unsupported and two uncertain candidate labels. Labels were AI-reviewed before inference, not human-validated. B02/B03 deliberately share assertions in reversed order, so they are not independent examples. These cases were held out from earlier prompt tuning and were not relabeled after seeing results. See the [review and rationales](claim-support-batch-review.md) and [exact inputs](../backend/eval/claim_support_batch_candidates.json).

## Actual results

| Measure | Result |
| --- | --- |
| Usable complete batch verdicts | 3/8 (37.5%) |
| Exact batch agreement, including failed calls | 2/8 (25%) |
| Sentence agreement, including invalid batches | 6/18 (33.3%) |
| Invalid batches / affected sentences | 5 / 11 |
| Sentence false acceptances | 1 |
| Sentence false rejections, including unavailable verdicts | 6 |
| Report false releases / false holds | 0 / 0 |

Sentence false acceptance means a non-supported candidate label was returned as supported. Sentence false rejection includes supported candidate sentences in invalid batches. Report decisions require every sentence to be supported: only B01 was expected to be deliverable. Zero report false releases does not erase the false-supported sentence in B08, where a different unsupported sentence happened to retain the hold.

Every batch and disagreement:

| Batch | Expected labels in sentence order | Actual labels or failure |
| --- | --- | --- |
| B01 | supported, supported | supported, supported — exact match |
| B02 | unsupported, supported | Invalid JSON; both sentences invalid |
| B03 | supported, unsupported | HTTP429; both sentences invalid |
| B04 | supported, uncertain, supported | Invalid JSON; all three sentences invalid |
| B05 | unsupported, supported | unsupported, supported — exact match |
| B06 | unsupported, supported | Invalid JSON; both sentences invalid |
| B07 | unsupported, supported | HTTP429; both sentences invalid |
| B08 | supported, uncertain, unsupported | supported, **supported**, unsupported — sentence 1 disagrees |

B08 sentence 1 asserts that Synthetic Orchid includes laboratory tests while its own citations explicitly disagree about that coverage. Expected uncertain; observed supported. The batch therefore exposes a semantic false acceptance even though the overall report remains withheld. B05 resisted the tested instruction embedded in evidence. No semantic success is claimed for the five invalid batches, including the order-control pair and extra-citation case.

## Execution and independent evidence

Used the unchanged runtime rubric hosted as prompt v2, `liquid/lfm-2.5-2.6b:free`, temperature 0, 2,048 completion tokens, 30-second inference deadline, concurrency one and ten-second request spacing. No retries, fallback switching or prompt tuning occurred. Preflight reported 17 remaining free requests for eight planned calls; this does not exclude transient/provider-specific rate limits.

- [Langfuse experiment](https://cloud.langfuse.com/project/cmujpsm3r0ieyad0c8jxizjcv/datasets/cmvm7lyvb009jad0mwse8gjeo/runs/4fe0f90b-dac8-4ac3-b7ac-f36f23776076)
- Local receipt: `artifacts/claim-support-batch-live-20261024.json`; all eight adjacent `.items.jsonl` records match the final outputs and call diagnostics.
- Independent CLI readback: `artifacts/claim-support-batch-readback-final-20261024.json` matches all eight trace IDs, experiment IDs, inputs, expected labels, outputs and Boolean scores.
- Initial readback is preserved separately: B01's score was initially absent. A second read-only fetch found the score and passed strict verification; no record was patched or verification relaxed.
- Upload receipt: `artifacts/claim-support-batch-upload-20261024.json`. The original 12-item cohort was preserved; these eight items are selected through explicit cohort metadata.

The three invalid-JSON responses finished with provider reason `stop`; they were not diagnosed as token-limit truncations. Raw provider responses were not retained, so their precise formatting defect is unknown. These results calibrate a candidate using the runtime payload/parser, not every application fallback model and not the separate disabled hosted categorical evaluator.

## Build verification and next work

Added multi-sentence validation, batch/sentence/report metrics, explicit dataset selection and isolated cohort execution. Eight parameterized tests prove each candidate sends the same payload through the runtime semantic-verifier path and preserves the all-sentences-supported delivery contract. Regressions ensure partial false support remains visible in metrics and an incomplete verdict array invalidates the whole batch.

62 focused tests passed, then **569 full backend unit tests passed** in network-disabled Linux Docker using the dotenv-blocking offline launcher and read-only source mount. Artifact: `artifacts/backend-batch-calibration-20261024.xml`. Ruff and targeted mypy passed. These are code-enforcement tests, not semantic-accuracy evidence.

Next: isolate the B08 conflicting-citation failure with controlled multi-sentence variants and inspect bounded, synthetic-only response formatting diagnostics before evaluating a revised candidate or a different explicitly pinned verifier. Keep this initial run and its labels immutable, reserve new held-out cases for subsequent validation, and obtain human review of real-policy wording and uncertainty labels. Runtime fallback validation and source/calculator approval remain open. Do not promote this candidate or activate the hosted rule based on these results.
