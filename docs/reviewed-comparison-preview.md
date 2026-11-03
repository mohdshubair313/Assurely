# Reviewed policy comparison preview

**Later checkpoint on 2026-11-02:** The separately documented
[reviewed policy-terms graph adapter](reviewed-policy-terms.md) now reads imported
reviewed values from `policy_terms` for an explicit scenario. This internal preview
still works as described below; graph delivery remains held until the report,
decision-trace and release checks are completed.

Checkpoint: 2026-11-02. This is an internal operator preview of explicit policy
scenarios, built on the publication gate. It is not a customer report or permission
to deliver one. It neither chooses policies for a customer nor infers missing
scenario details.

`POST /v1/policy-publications/comparisons` requires the existing verified reviewer
identity and operator allowlist. The request contains `items`, one to five distinct
publication digests, each with its own one to three supported capabilities and
explicit `context`. Its JSON body is bounded to 64 KiB, duplicate JSON keys and
extra fields are rejected, and no client-supplied issuer or approval is trusted.

```json
{
  "items": [
    {
      "publication_digest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "capabilities": ["coverage_options", "base_ped_wait"],
      "context": {
        "transaction": "issue",
        "transaction_date": "2026-11-02",
        "cover_basis": "individual",
        "selected_options": [],
        "residency": "resident"
      }
    }
  ]
}
```

The digest above is a format example only. Issue/renewal, date, cover basis and
selected options are mandatory. Other predicate inputs remain unknown when omitted;
they are never filled from a model, current date, customer profile or another policy.
Each item can describe different optional benefits. Duplicate digests or capabilities
are rejected so the result cannot silently merge separate scenarios.

For every requested capability, the service calls the existing fresh publication
lookup in the same transaction. The result preserves caller item order and reports
`complete`, `partial`, or `unavailable` **only for the requested capabilities**.
Unavailable capabilities contain no facts and retain their specific gate reason;
unknown or foreign-issuer digests are indistinguishable as `not_found`. No seed
lookup, score, premium, personal coverage or eligibility verdict is produced.

Available results retain discrete paise coverage options, exact age basis and
original day/calendar-month units. Every fact retains its original source quote,
PDF hash, URL, human-review date and event identity. The existing publication
lookup also now includes `scope_review`: separate applicability and condition
evidence plus any identity/condition note mappings and their evidence, bound to the
same human-review event. This keeps the provenance of an interpretation visible
alongside the source of the underlying value. It does not establish the correctness
of a human interpretation or make a partial product record complete.

The comparison obtains issuer/identity advisory locks in sorted order before it
obtains individual draft locks. It performs final publication-state and expiry
checks across the entire preview; expiry during a longer comparison clears the
affected facts. Review changes and revocation serialize against its transaction.
The resulting preview has `requires_fresh_lookup: true` and
`customer_delivery_authorized: false`: a later decision or delivery must recheck
the live gate. No preview is stored as an approval credential.

## Integration boundary and next work

This checkpoint adds the comparison service and an internal reviewer endpoint,
not a graph or frontend connection. Non-development `compare_verify` remains
blocked and Stage 4 continues holding customer delivery. The current graph intake
does not have trustworthy issue/renewal dates or selected-option input; it would be
unsafe to guess them from existing profile fields.

The published facts currently reside in the reviewed publication/source tables.
The project's hard rule requires deterministic `policy_terms` lookups for customer
policy facts. Before exposing these facts in graph output, flag the necessary schema
or adapter change and reconcile that rule with the unit-preserving representation;
do not flatten discrete cover options or calendar months into legacy min/max/day
columns. The reviewed report adapter also needs sentence-level provenance and a
fresh gate at release, without changing graph routing or allowing guardrail to write
output. Graph state, routing, `policy_terms`, application database migrations and
frontend were not changed here.

The focused test suite includes authenticated HTTP requests against a real isolated
Postgres instance, revocation and late-expiry withholding, conditional missing
input, competing input order, source evidence and calendar-unit preservation.
All review decisions in these tests use synthetic identities and policy evidence.
See `PROGRESS.md` for test count and artifact. No real insurer policy was approved.
