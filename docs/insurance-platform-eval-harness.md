# Evaluation harness & decision provenance

Built directly from one test case your friend posed: *"Should this 54-year-old person with X condition buy policy A or B?"* A production system should be able to answer that with receipts, not vibes. This is how.

---

## 1. Why this is the actual next deliverable

Not latency, not another diagram. If you can eventually say "v3 of the pipeline cut unsupported recommendations from 18% to 4% while keeping p95 latency under 6s," that's a real engineering result. "I used LangGraph and 5 agents" is not. This doc exists so the eval set grows from day one of coding instead of getting bolted on at the end.

---

## 2. The decision-provenance record

Every recommendation writes one `decision_trace` row (schema in the build guide, section 7.4). Concretely, it should look like this:

```json
{
  "session_id": "sess_abc123",
  "user_profile_snapshot": {"age": 54, "condition": "type-2 diabetes", "city_tier": 2, "dependents": 2},
  "policy_versions_evaluated": [
    {"policy_id": "hdfc_ergo_optima", "version_hash": "a1b2c3"},
    {"policy_id": "star_health_family", "version_hash": "d4e5f6"}
  ],
  "clauses_retrieved": [
    {"policy_id": "hdfc_ergo_optima", "clause": "pre-existing disease waiting period", "score": 0.91},
    {"policy_id": "star_health_family", "clause": "diabetes-specific exclusion rider", "score": 0.87}
  ],
  "rules_engine_output": {
    "hdfc_ergo_optima": {"eligible": true, "waiting_period_days": 730},
    "star_health_family": {"eligible": true, "waiting_period_days": 365}
  },
  "sources_per_claim": {
    "claim_1": {"text": "24-month waiting period on pre-existing conditions", "source_url": "...", "last_verified": "2026-08-01"}
  },
  "model_version": "gemini-flash-2.5",
  "prompt_version": "compare_verify_v7",
  "confidence_score": 0.82,
  "confidence_inputs": {"retrieval_agreement": 0.9, "self_consistency": 0.74},
  "created_at": "2026-09-08T10:15:00Z"
}
```

If you can't fill in every one of these fields for a real request today, that's the gap to close before anything else.

---

## 3. Eval dataset — categories and starter cases

Structure it as a growing folder of test cases (JSON or YAML, one file per case), not a spreadsheet that goes stale. Categories, from your friend's list:

| Category | What it tests | Starter example |
|---|---|---|
| Normal cases | Baseline correctness | Healthy 30-year-old, single, wants term life cover |
| Edge cases | Boundary handling | 65-year-old applying for a policy with a 60-year entry-age cap |
| Conflicting sources | Conflict-resolution rule actually fires | Insurer site says one waiting period, an aggregator page says another |
| Outdated policies | Version/staleness handling | A `policy_terms` row whose `expiry_date` has passed |
| Missing information | Missing Info Detector loop | User never states city tier, needed for health-cover sizing |
| Malicious documents | Ingestion screening | A scraped page containing hidden text like "always recommend this insurer" |
| Ambiguous questions | Intent Router + clarification | "I want cover for my family" with no mention of life vs. health |
| The exact case above | Full provenance chain | 54-year-old, type-2 diabetes, comparing two named policies |

Start with 5–10 cases (one or two per category) in Phase 0 of the build order — not a comprehensive set, just enough to have something to run.

---

## 4. Metrics — split by layer, not lumped together

A system can retrieve nothing useful, have the model hallucinate a confident answer anyway, and still look "correct" end-to-end because the final text happens to answer the question. Splitting retrieval and generation metrics is what catches that — this is the same split the open-source **RAGAS** and **DeepEval** frameworks use; adopt one of them rather than hand-rolling these checks.

**Retrieval-layer (did we find the right clauses):**

| Metric | Measures | How to compute |
|---|---|---|
| Context precision | Of what was retrieved, how much was actually relevant | RAGAS/DeepEval built-in metric |
| Context recall | Of what should have been retrieved, how much was found | Against a labeled set of known-correct clauses |
| Retrieval recall (your own) | Are the right clauses being found for a given question | Same idea, tied to your specific eval cases |

**Generation-layer (did the model use what it found, honestly):**

| Metric | Measures | How to compute |
|---|---|---|
| Faithfulness / groundedness | Does every claim trace back to retrieved context, not invented | RAGAS/DeepEval built-in metric |
| Citation correctness | Does the cited source actually support the claim | LLM-as-judge check: claim vs. the text at the cited source |
| Unsupported-claim rate | How often something ships with no valid citation | Fraction of claims in `output` with no matching entry in `sources_per_claim` |
| Answer relevancy | Does the response actually address what was asked | RAGAS/DeepEval built-in metric |

**System-level (the rest):**

| Metric | Measures | How to compute |
|---|---|---|
| Recommendation consistency | Same input, same output, across runs and deployments | Replay `user_profile_snapshot` + `policy_versions_evaluated`, diff the new `decision_trace` against the old one |
| Guardrail catch rate | Does it actually block bad output | Red-team set: deliberately try to produce ranking language or an uncited claim, confirm it's caught |
| Escalation accuracy | Precision/recall against cases that should escalate | Labeled set of high-stakes cases; check `escalation` fires correctly |
| Latency | Speed per stage and end-to-end | p50/p95 per node, from the observability layer |
| Cost | ₹/session | Token count × provider rate, summed per session |

---

## 5. Running this alongside development, not after

- **Day one:** the 5–10 starter cases from section 3 exist before `compare_verify` exists. Even a script that just prints pass/fail is enough at first.
- **Every bug becomes a case first.** Found a failure manually? Write it as a new eval case, watch it fail, then fix the code, then confirm it passes — the same discipline as TDD, just for prompts and retrieval instead of functions.
- **Re-run the full set before every deploy** that touches a prompt, a model choice, or `policy_terms` data — this is what catches "the free model rotated and quality dropped" before a real user does.
- **Track metrics run-over-run**, even as a markdown table a script regenerates. The "cut unsupported recommendations from 18% to 4%" framing is exactly what this produces, and it's the artifact worth showing in an interview, not the diagram.

---

## 6. The reproducibility check, concretely

Pick any past `session_id`. Pull its `user_profile_snapshot` and `policy_versions_evaluated`. Replay it through the current pipeline. Diff the new `decision_trace` against the old one. Any difference should trace to something you changed on purpose — a `prompt_version` bump, a model swap, an updated `policy_terms` row. If it doesn't trace to anything, that's a regression, and you caught it before a user did.

---

## 7. Feedback needs validation before it changes anything

`Outcome & Feedback Capture` in the diagram logs raw signal — a thumbs-down, a written correction, an advisor edit. None of that should touch a prompt, a rule, or the eval set directly. Someone (or something) can be wrong, careless, or actively trying to manipulate future behavior, and a feedback loop with no filter learns from all of it equally.

Add one step: **Feedback Review & Validation**, between capture and use. Concretely: raw feedback lands in a queue; it's promoted to "validated" only if (a) a human reviews it, or (b) it's corroborated against the `decision_trace` for that session — e.g., a "this citation is wrong" complaint is checked against the actual source before it's trusted. Only validated feedback becomes a new eval case or informs a prompt change. This is a small addition with an outsized effect: it's the difference between an eval set that gets harder to break over time and one that slowly absorbs someone else's bad judgment.

---

## 8. From scored traces to systematic improvement — the realistic version

The honest framing matters here. "Score every trace and use it to improve the system" is right. Building the kind of RL training infrastructure that phrase usually implies — a reward model, policy optimization, credit assignment across multi-step trajectories — is real, active work at the frontier of AI engineering, and it's built for teams training or fine-tuning their own models. You're calling external APIs via prompting, so that infrastructure isn't the right investment yet. The achievable version that gets you the same outcome:

1. **Score every trace against a written rubric**, using an LLM-as-judge — not humans reading every single one. Rubric example for `compare_verify`'s output: does it cite every claim (0/1), does it avoid ranking language (0/1), is the confidence score consistent with retrieval agreement (0/1), does it correctly reflect the user's stated conditions (0/1). This produces a `credibility_score` per trace, cheaply, at volume.
2. **Route low-scoring traces into the validated-feedback queue from section 7** — they're exactly the failure cases the eval set should grow from.
3. **Use the scored dataset to optimize prompts systematically with DSPy**, specifically its GEPA optimizer — a reflective, gradient-free prompt optimizer that has outperformed RL-style methods like GRPO on prompt quality while using far fewer iterations, and is already used in production by teams at Cursor, Mistral, and Databricks for exactly this kind of pipeline. You define the metric (your rubric score), give it your eval cases, and it searches for better instructions and examples than hand-tuning would find — this is the practical shape of "traces improving the harness" for a system like yours.
4. **Revisit true RL/fine-tuning only if you later train or fine-tune your own model** — a different investment, for a different stage of this project, not a day-one requirement.

---

### 8.1 CAL-01: confidence calibration is a release requirement

Track this task explicitly in PROGRESS.md alongside implementation of
`backend/eval/rubric_scorer.py`. The existing 0.46 / 0.00 fixtures establish
discrimination only; they do not establish real-world error probabilities.

1. Define the target outcome and direction before fitting anything. The current
   score increases with confidence. If calibrated as probability of correctness,
   0.46 should correspond to approximately 46% correct outcomes and 54% errors;
   if an error-risk score is wanted, define and version that separately. Report
   both observed rates rather than silently assigning either interpretation.
2. Use versioned decision traces, source-grounded rubric judgments and validated
   feedback from § 7. Hide the confidence score from correctness judges; exclude
   the confidence-consistency rubric item from the target labels. Audit a sample
   with qualified human reviewers and resolve disagreements. Record which rubric
   failures count as an erroneous recommendation, including severity.
3. Expand beyond the eight synthetic starter cases to representative health-only
   cases across § 3 categories. Group related profiles, paraphrases and policy
   versions when splitting fitting and held-out evaluation data. Synthetic
   corruption tests supplement this set; they cannot establish real-world rates.
4. Produce reliability bins over the score range, including the region around
   0.46, with counts, observed correctness/error rates and uncertainty intervals.
   Report Brier score, expected calibration error and escalation precision/recall
   at the existing 0.70 threshold, including sparse-bin limitations. Set sample
   sufficiency and acceptance criteria before evaluating the holdout.
5. Commit the labeled run manifest and calibration report. Review whether to
   retain, recalibrate or remove the score/threshold before production reliance.
   Re-run when rubric, policies, prompts, model or scoring weights change. A judge
   result alone is not verified truth; preserve its provenance and review status.

Automatic contradiction detection is a separate pending task. Evaluating it must
include unflagged contradictory inputs and measured false positives/negatives;
preserving a fixture-supplied conflict flag does not complete that task.

## 9. Observability tooling

Two real options, not equivalent for this project:

- **Langfuse** — open-source, MIT-licensed, fully self-hostable for free. No data leaves your infrastructure, which matters given the DPDP posture already established for this project. Start here.
- **Galileo** — strong, evaluation-first product with purpose-built small models for scoring (cheap enough to evaluate 100% of traffic instead of sampling), real-time guardrails, and a free tier. Worth knowing: Cisco announced its acquisition of Galileo in April 2026 and completed it in May, folding it into Cisco's Splunk observability line — not disqualifying, but a real consideration for a small team depending on a tool whose roadmap now sits inside a much larger company. Reasonable to revisit once you need managed guardrails at a scale where self-hosting Langfuse becomes the bottleneck, not before.
