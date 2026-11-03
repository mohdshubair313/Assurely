# Policy source review package v1

**2026-10-30 update:** The unchanged source-review validator now feeds an offline typed normalization/import-preparation layer. Actual Care/HDFC/Star drafts contain 6/6/5 typed proposals respectively; all remain unapproved. See [shared policy-rule/import contract](policy-rule-import-contract.md) for implemented behavior, proposed persistence and next acceptance gates. The earlier counts and first-package results below remain historical.

**2026-10-26 update:** Care now has five extracted proposals; HDFC and Star packages
have four and five respectively. All three pass actual-file validation. See the
[field extraction review](policy-source-extraction-review.md) for remaining gaps
and source discrepancies. The first-package counts below describe the initial run.

Implemented 2026-10-25 in `backend/app/db/source_review.py`. This is an offline pre-import review format, not a database migration or import endpoint. No database, application Settings, network or model is accessed by validation. Existing RAG ingestion screening remains a separate control.

Each package identifies the insurer/product and requires ten explicit fields: UIN, variant, effective date, expiry date, sum-insured options, adult minimum/maximum entry age, PED waiting period, exclusions and premium table. A field is either extracted with proposed text, units and PDF evidence, or missing with an explanation. A missing expiry date does not mean open-ended validity. Missing premium data does not mean free cover.

Proposed values deliberately remain text. They are not ready for insertion into numeric database columns. Waiting periods retain `days` or `calendar_months`; no automatic conversion to 1,095 days exists. Calendar arithmetic, normalized premium dimensions, variant interpretation and database migration remain separate work.

## Validation

- Reject unknown properties, duplicate JSON keys, repeated/missing required fields and incompatible units.
- Require exact supplied source set, HTTPS URLs without credentials, SHA256 hashes and non-future access dates.
- Match the hash against bounded PDF bytes, verify actual page count and match each quoted excerpt on its one-based physical PDF page using whitespace normalization.
- Accept publicly readable permission-encrypted PDFs with an empty read password; reject files needing a private read password.
- Require date values to parse and reject expiry before effective date when both are supplied.
- Reject any review status other than `pending_human_review`. Return explicit missing/unresolved fields, a package digest and approval flags false.

This proves byte consistency and excerpt location, not authenticity, factual interpretation, completeness of conditions or suitability. Page text matching is not source approval. A hash does not establish that a URL served those bytes; acquisition provenance and authenticated review remain necessary. Raw PDFs must still pass existing ingestion screening before RAG use. The package does not invoke or replace that screening.

## First real package

`backend/data/source_reviews/care-supreme-candidate.json` pins the current Care PDF retrieved from the official index's link. Standard PDF request headers resolved the previous HTTP406. It contains UIN CHIHLIP27061V032627 and a proposed base PED period of 36 calendar months with continuity/schedule conditions retained as review notes. Both fields remain pending human review; eight other fields are explicitly missing.

Evidence:

- PDF and acquisition receipt: `artifacts/source-audit-20261024/care-supreme.pdf`, `care-receipt.json`.
- Real-byte validation: `artifacts/care-source-review-20261025.json`; structural validation passed, import/production approval false.
- 18 focused tests: `artifacts/source-review-contract-final-20261025.xml`. These cover fabricated hashes/quotes/page counts, unknown sources, ambiguous JSON, false approval, units, missing data and encrypted-source behavior. Ruff and targeted mypy passed.

## Next gate

Extract remaining applicable Care fields and stage HDFC/Star packages against their archived bytes. Establish all effective-date, variant, premium-input and condition evidence; review calculator assumptions separately. Before a database importer, explicitly design the UIN/variant identity, calendar-period representation and authenticated approval record bound to the exact package digest. Never accept a JSON `approved` flag as reviewer identity. Priorities 3 and 4 remain queued behind source/calculator approval.
