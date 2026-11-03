# Ordered backend completion gates

User priority, 2026-10-24. Complete in this order; do not confuse investigation closure with permission to release.

1. **Current multi-sentence candidate: rejected; runtime containment implemented and validated.** The fixed cohort must have 100% usable complete outputs, zero sentence false acceptances, zero report false releases, at least 85% exact batch agreement and at least 80% agreement for each label. These are engineering screening thresholds, not a statistical or regulatory safety guarantee. Passing permits further validation only. Human-reviewed real wording, new held-out cases and every actual fallback model remain production gates. `eval.claim_support_acceptance.assess` recomputes criteria from inputs and actual verdicts. A failed candidate is closed as rejected, never promoted.
2. **Source/calculator verification: audit underway; approval open.** Match insurer-issued documents to UIN, variant, policy-period applicability and exact bytes/hash; distinguish source access date from insurer validity. No synthetic premium table or invented effective date may be promoted. Verify every calculator assumption separately; arithmetic correctness cannot establish suitability. Qualified review remains necessary for real-user use.
3. **Auth, durable state, advisor release: queued.** Validate real identity/ownership, restart persistence, idempotent notification and authenticated human release with auditable state transitions. Flag schema/routing changes before implementation. No deployment from test-only credentials.
4. **Frontend integration and end-to-end journey: queued.** Connect authenticated endpoints, test intake through comparison, report hold and advisor release, restart/expiry and failures. Final release requires all earlier production gates; a visual demo is not production acceptance.

## Current calibration closure

The minimal conflict clarification (candidate prompt v4) was tested on the unchanged eight batches. It yielded 2/8 usable arrays, 1/8 exact batches, 3/18 exact sentences, one sentence false acceptance and one report false release (B07). Four invalid outputs were code-fenced JSON and two calls returned HTTP429. Every criterion failed; candidate rejected. Strict parsing was preserved: fenced outputs were not repaired into passing verdicts. The cloud rule remains disabled and the candidate was not copied into runtime.

Observed failure: an LLM can favor one citation while ignoring a contradictory or irrelevant companion. Runtime containment now returns uncertain for a sentence with multiple distinct normalized citation statements before invoking the model. This also withholds compatible composite evidence; that deliberate limitation avoids pretending to solve general semantic reconciliation. Identical statements remain eligible. No schema, graph edge or provider routing changed. Single-citation semantic judgments remain uncalibrated and are not production-approved.

Evidence: `artifacts/claim-support-conflict-live-20261024.json`, `claim-support-conflict-readback-20261024.json`, `claim-support-conflict-acceptance-20261024.json`. The live experiment tests the candidate prompt, not the subsequently added deterministic containment. Runtime regressions validate containment separately.

[Candidate prompt v4](https://cloud.langfuse.com/project/cmujpsm3r0ieyad0c8jxizjcv/prompts/prompt-detail?promptName=judge-calibration%2Fclaim-support&version=4) · [Experiment](https://cloud.langfuse.com/project/cmujpsm3r0ieyad0c8jxizjcv/datasets/cmvm7lyvb009jad0mwse8gjeo/runs/8a75dba0-8205-4241-886c-ec7eb028c1c0).

| Dataset input | Expected output | Actual output |
| --- | --- | --- |
| B01 independent faithful paraphrases | supported, supported | supported, supported |
| B02 cross-policy contamination | unsupported, supported | Invalid code-fenced output |
| B03 reversed B02 order | supported, unsupported | Invalid code-fenced output |
| B04 missing benefit detail | supported, uncertain, supported | HTTP429 |
| B05 instruction embedded in evidence | unsupported, supported | HTTP429 |
| B06 instruction embedded in sentence | unsupported, supported | Invalid code-fenced output |
| B07 faithful claim plus unrelated citation | unsupported, supported | supported, supported |
| B08 same-policy conflicting citations | supported, uncertain, unsupported | Invalid code-fenced output |

Exact dataset inputs and frozen labels: [candidate JSON](../backend/eval/claim_support_batch_candidates.json). No failed case was removed from denominators or relabeled.
