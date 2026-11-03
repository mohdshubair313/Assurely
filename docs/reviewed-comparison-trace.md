# Reviewed comparison decision trace

Checkpoint: 2026-11-02. Maintenance of `persist_memory` only; no database schema or
graph routing changes. Uses the existing decision-trace JSONB fields.

- `policy_versions_evaluated_json` records the publication digest, policy term row,
  capability, review event and actual review date for each available lookup.
- `sources_per_claim_json` adds namespaced lookup-fact entries so identical fact
  names across policies/capabilities cannot overwrite each other. Each entry is
  labelled `lookup_fact_not_generated_claim`: report claim support is a separate
  concern. Original numeric values and units are preserved without conversion.
- `rules_engine_output_json.reviewed_comparison` records historical status,
  timestamps, expiry, available/unavailable outcomes and reasons. Fact references
  and applicability/condition references remain separate, including the reviewed
  note-resolution mappings. Unknown source-reference fields are excluded.

The audit always says `customer_delivery_authorized=false` and
`requires_fresh_lookup=true`. It never refreshes policy validity during persistence:
doing so would replace the evidence used in the completed lookup. Source presence
and matching term/review identifiers determine the `provenance_complete` structural
marker; this marker does not validate source authenticity or approve a report.
Missing evidence remains missing. Unavailable results never retain leftover facts.

Personal scenario inputs are not copied into this projection. Publication digests
locate immutable policy scope; this record alone cannot replay personal condition
evaluation. Existing user profile snapshot and consent behavior are unchanged.
Rejected turns and accepted turns exiting for missing intake fields, life scope or
unclear intent omit reviewed comparison provenance from prior checkpoints.

Validation: 26 focused tests covering projection and mocked ORM persistence plus
existing rejected-input tests. No live database migration or insurer approval was
performed. Evidence: `artifacts/reviewed-trace-tests-20261102.xml`.

Next: implement the reviewed report adapter in its own node session. Delivery must
remain held until a separate fresh publication/applicability/condition check is
wired at release. Migration 006, real insurer publication and calculator review
remain pending as documented in PROGRESS.md.
