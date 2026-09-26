"""Rubric-based trace scorer — LLM-as-judge scoring per eval harness § 8.

Scores every decision_trace against a written rubric using an LLM-as-judge
(not humans reading every single one). Produces a ``credibility_score``
per trace, cheaply, at volume.

Example rubric for compare_verify output:
  - Does it cite every claim?           (0/1)
  - Does it avoid ranking language?     (0/1)
  - Is confidence consistent with retrieval agreement?  (0/1)
  - Does it correctly reflect the user's conditions?    (0/1)

Low-scoring traces are routed into the validated-feedback queue
(eval harness § 7) — they're exactly the failure cases the eval
set should grow from.

The scored dataset feeds DSPy/GEPA prompt optimization in Phase 5.
"""
