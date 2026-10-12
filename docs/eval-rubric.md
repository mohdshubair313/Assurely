# Health advisory rubric v3

This offline scorer supplements the October 9 RAGAS baseline. It evaluates real final-turn
reports from the existing graph, including reports held from delivery. It does not change
production routing, delivery, storage schemas, or confidence thresholds.

## Written criteria

Each criterion returns a Boolean and a fixed reason code. Inspect retrieval and generation
separately; a supported statement can still fail to answer the user's question.

| Layer | Criterion | Pass condition / intended failure |
|---|---|---|
| Retrieval | `query_topic_coverage` | Requested topics and named policies have relevant clause evidence. Case 04's room-rent/restoration chunks fail its waiting-period question. |
| Retrieval | `reference_clause_coverage` | Required reference wording is covered by retrieved clauses; respect explicitly documented corpus gaps. Probe cases 01/08's incomplete coverage. N/A without a reference. |
| Generation | `question_answered` | Covers requested topics/entities or explicitly explains evidence limitations. Sourced unrelated advice and silent omissions fail. |
| Generation | `claims_grounded` | Claims agree with the full sourced evidence packet, including deterministic policy terms. This is fixture grounding, not external policy verification. |
| Generation | `profile_fidelity` | Captured profile and advice do not contradict declared age, conditions or family needs. |
| Generation | `scenario_handled` | Handles conflict, entry-age eligibility, expired-product question, injection, or named-policy comparison as applicable. |
| Generation, clarification only | `appropriate_clarification` | Requests missing required profile information or clarifies health/life intent. |
| Generation, clarification only | `no_premature_advice` | Makes no unsupported recommendation or numeric policy claim before clarification. |
| Controls, deterministic | `citations_complete` | Every generated sentence has citations matching the actual evidence catalog, including valid verification dates. N/A for clarification. |
| Controls, deterministic | `need_fit_language` | No prohibited comparison terms, including punctuation-delimited occurrences. |

Cases 03/07 use only the clarification generation criteria. Other cases use four report
generation criteria. Retrieval references are absent for 02/05/06: reference coverage is N/A,
but query-topic coverage is still scored because these cases actually retrieve clauses.

`layer_scores` report retrieval and generation means separately. `credibility_score` is the
equal-weight mean of generation and applicable deterministic controls; retrieval is never
blended into it. Any failed criterion, including retrieval, makes a local `review_candidate`.
These candidates await validated feedback review; they are not inserted into a production
feedback queue or accepted automatically as verified labels.

## Judge, privacy and provenance

- One OpenRouter request per case, pinned to `nvidia/nemotron-3-super-120b-a12b:free`, with
  low reasoning effort and a 4,096-token completion cap; no judge fallback or blind retries.
  A missing/nonzero returned cost, incomplete/empty response, unexpected model, or invalid
  schema stops the run as an evaluator error, never a zero quality score.
- V3 gives only retrieval criteria zero-based `retrieved_indices`. Generation verdicts
  contain only a Boolean and fixed reason code; the judge still sees the full sourced
  generation evidence and answer text. This avoids emitting long ID and sentence-index
  lists while keeping the generation assessment grounded in the complete input. Each
  packet receives a strict JSON schema; local validation remains mandatory. The endpoint
  preflight requires structured-output support and provider routing requires parameter
  support. The v2 case-01 response ended at its 4,096-token cap, so this version shortens
  verdicts instead of increasing the per-case or full-run token budget.
- Malformed references report fixed validation-reason codes and allowed/received counts,
  never the invalid values or raw judge text. Packet array counts are retained for diagnosis.
- Judge sees whitelisted query/profile/report/evidence fields; confidence, confidence inputs,
  guardrail notes, approval and escalation fields are excluded. Treat all supplied text as
  untrusted data, including injection fixtures. No free-text judge explanations are accepted.
- Artifact stores fixed reason codes, evidence indices, packet digest, rubric/prompt versions,
  provider/model usage and trace IDs; no request/profile/answer bodies or API keys. Real
  clause/citation content remains in the existing operational Postgres trace rows. Full
  historical report text is not stored there, so this implementation uses an ephemeral live
  handoff. Historical bulk scoring/human answer inspection requires a live handoff or a
  separately reviewed persistence contract; no such schema change is made here.
- One verdict belongs to the final turn identified by `judged_trace_id` and
  `judged_decision_trace_id`. Earlier intake-turn IDs are provenance only, not copies of that
  final-turn verdict. Database verification records all turns' model/prompt/policy versions;
  source and reference digests identify the evaluated checkout and fixture contract. Langfuse
  verification uses the CLI's content-free observation core fields.
- All labels are `unreviewed_fixture_judge_candidate`. CAL-01 remains open: neither these eight
  synthetic cases nor judge agreement establishes real-world calibration. Independent human
  validation, representative holdout data and predeclared acceptance criteria remain required.
  Confidence-consistency is deliberately excluded from correctness labels to avoid circularity.

Design references: [Langfuse judge guidance](https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge),
[writing evaluators](https://langfuse.com/academy/evaluate/writing-evaluators),
[OpenRouter free variant](https://openrouter.ai/docs/guides/routing/model-variants/free),
[OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs).

## Windows run instructions

Use the [beginner run guide](run-rubric-evaluation.md). The preflight makes no LLM calls.
The full batch starts with cases 04/01/08, waits 60 seconds after each pipeline execution,
and spaces cases by 180 seconds. It writes checkpoints to one result file and stops on the
first unrecovered pipeline/judge error; preserve that file instead of repeatedly rerunning.
