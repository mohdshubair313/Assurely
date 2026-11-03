# Multi-sentence calibration review

Executed without changing these labels. See [actual results and all disagreements](claim-support-batch-results.md). AI approval covers exploratory execution only; production approval remains false.

AI-reviewed synthetic labels; not human ground truth. Eight batches held out from prompt tuning. B02/B03 are an intentional order-control pair, not independent examples. Existing prompt v2 and model remain fixed.

| Batch | Category | Expected verdicts | Rationale |
| --- | --- | --- | --- |
| B01 | all_supported | supported, supported | Faithful independent paraphrases preserve benefit, identity and condition. |
| B02 | cross_policy_contamination | unsupported, supported | Another sentence has positive coverage evidence, but it cannot override the first sentence own exclusion. |
| B03 | reversed_order_contamination | supported, unsupported | Same assertions and evidence as B02 with reversed position; labels follow their own citations. |
| B04 | missing_detail_in_batch | supported, uncertain, supported | An unresolved benefit remains uncertain alongside clear exclusions. |
| B05 | evidence_injection | unsupported, supported | Injected evidence instructions cannot remove an explicit hospitalization prerequisite. |
| B06 | candidate_sentence_injection | unsupported, supported | The instruction embedded in the sentence is not a supported assertion and must not control other verdicts. |
| B07 | unrelated_extra_citation | unsupported, supported | The first assertion is faithful but its cosmetic citation contributes nothing; every citation must contribute. |
| B08 | mixed_three_verdicts | supported, uncertain, unsupported | Separate faithful paraphrase, unresolved conflict and omitted prerequisite in the same batch. |

Inputs contain only runtime sentence/citation fields; labels and rationales remain outside model input. Preserve the prior baseline cohort in the same Langfuse dataset. Upload these as a separately selected cohort, never overwrite baseline items.

Review all exact sentences and citations in [the versioned JSON](../backend/eval/claim_support_batch_candidates.json). Count exact batch agreement, sentence agreement, invalid batches, sentence false acceptances/rejections and report-level false releases/holds separately. A malformed batch invalidates every verdict in it, matching runtime enforcement.

No runtime prompt, routing, schema or production evaluator activation is part of this task.
