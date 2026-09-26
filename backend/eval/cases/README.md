# Eval Cases

This directory holds the growing set of test cases (JSON or YAML, one file per case).

Categories from the eval harness doc (§ 3):
- Normal cases — baseline correctness
- Edge cases — boundary handling
- Conflicting sources — conflict-resolution rule firing
- Outdated policies — version/staleness handling
- Missing information — Missing Info Detector loop
- Malicious documents — ingestion screening
- Ambiguous questions — Intent Router + clarification
- Full provenance chain — the "54-year-old with diabetes" case

Start with 5–10 cases (one or two per category) in Phase 0.
Every bug becomes an eval case first (§ 5).
