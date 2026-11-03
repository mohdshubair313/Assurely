# Offline policy evidence commands

These commands read explicitly supplied local PDFs. They require the existing Python dependencies, without Settings, environment credentials, network, models or database access. Outputs are review artifacts, not policy imports or customer quotes.

From the repository root, using the backend Python environment:

```powershell
backend/venv/Scripts/python.exe backend/tools/collect_policy_evidence.py --plan backend/evidence_plans/hdfc_optima_secure.json --source wording=artifacts/source-audit-20261024/hdfc-optima-secure.pdf --source prospectus=artifacts/source-audit-20261026/hdfc-prospectus.pdf --output artifacts/hdfc-rule-evidence-NEW.json --extracted-on YYYY-MM-DD

backend/venv/Scripts/python.exe backend/tools/extract_hdfc_base_grid.py --pdf artifacts/source-audit-20261026/hdfc-prospectus.pdf --output artifacts/hdfc-base-grid-NEW.json

backend/venv/Scripts/python.exe backend/tools/collect_policy_evidence.py --plan backend/evidence_plans/care_supreme.json --source wording=artifacts/source-audit-20261024/care-supreme.pdf --source prospectus=artifacts/source-audit-20261026/care-prospectus.pdf --source revision_rationale=artifacts/care-review-20261028/care-revision-rationale.pdf --output artifacts/care-rule-evidence-NEW.json --extracted-on YYYY-MM-DD
```

Replace the date and output names. Existing outputs are never overwritten. Raw PDFs and generated evidence stay excluded from Git; plans and extraction code are versioned.

`collect_policy_evidence.py` checks source hashes, page counts, ranges and unique exact boundary anchors, then retains original text fragments and page/character positions. Intermediate pages deliberately retain headers and footers; they are not reconstructed into prose. Full continuation text preserves qualifications that a short excerpt could lose. Tables still need visual interpretation.

`extract_hdfc_base_grid.py` accepts only the pinned 291-page prospectus and the base Optima Secure Plan pages 69-92. It preserves complete multiline geographic headings, the eight cover columns, source age labels, source rows and physical pages. Price values remain gross values as printed. It does not compute adjustments, resolve addresses or establish eligibility. This code replaces the earlier one-off extraction script under ignored `artifacts/` for future reproduction.

Both commands fix review/import/production status to pending/false. The `premium_table` and `exclusions` review fields remain missing until interpretation, applicability and required review are completed. Do not rerun old one-off staging scripts against the current candidate: they contain historical checkpoint notes and may replace current metadata.

Validation at the 2026-10-27 checkpoint: executed against archived PDFs; source collector produced ten sections / 28 page fragments, tariff extractor produced 546 rows / 4,368 cells, all price coordinates matched the earlier grid, and targeted Ruff checks passed. Unit and integration suites were deferred at the user's request. This is not a general PDF parser qualification or production readiness claim.

Care checkpoint, 2026-10-28: the pinned plan produced 21 sections / 91 fragments across wording, prospectus and the exact-UIN revision notice. It retains conditional exclusions, all optional benefits, pricing qualifications, claim-assessment order and illustrative prices. All fragments and 22 essential qualifiers were checked; eight rejection probes and actual candidate/PDF validation passed. The complete tariff remains unavailable; the product revision date is not an individual policy inception date. See `docs/care-supreme-source-review.md` for discovery receipts, visual checks, conflicts and next work.

## Prepare normalized rule drafts

`prepare_policy_import.py` validates a candidate against actual PDFs, normalizes only supported representations, and writes a draft plus a **blocked** import preview. It never imports data or grants approval. Preserve the original evidence, conditions and unresolved notes; a typed value remains a proposal.

```powershell
backend/venv/Scripts/python.exe backend/tools/prepare_policy_import.py --package backend/data/source_reviews/care-supreme-candidate.json --source wording=artifacts/source-audit-20261024/care-supreme.pdf --source prospectus=artifacts/source-audit-20261026/care-prospectus.pdf --source revision_rationale=artifacts/care-review-20261028/care-revision-rationale.pdf --as-of YYYY-MM-DD --output artifacts/care-rule-draft-NEW.json

backend/venv/Scripts/python.exe backend/tools/prepare_policy_import.py --package backend/data/source_reviews/hdfc-optima-secure-candidate.json --source wording=artifacts/source-audit-20261024/hdfc-optima-secure.pdf --source prospectus=artifacts/source-audit-20261026/hdfc-prospectus.pdf --as-of YYYY-MM-DD --output artifacts/hdfc-rule-draft-NEW.json

backend/venv/Scripts/python.exe backend/tools/prepare_policy_import.py --package backend/data/source_reviews/star-comprehensive-candidate.json --source wording=artifacts/source-audit-20261024/star-comprehensive.pdf --source prospectus=artifacts/source-audit-20261026/star-prospectus.pdf --as-of YYYY-MM-DD --output artifacts/star-rule-draft-NEW.json
```

Replace the date and output name; an existing output is never overwritten. To recheck a saved artifact, pass its `draft` object serialized as JSON and the actual PDF byte map to `app.db.policy_rule_draft.assess_draft(..., as_of=date(...))`. Do not trust its saved `import_preview` as an approval credential. The current implementation always withholds import, including for complete synthetic proposals. The contract and proposed migration/review protocol are in `docs/policy-rule-import-contract.md`.

The 2026-11-02 durable staging API can persist these drafts and original PDF bytes behind verified identity and an explicit reviewer allowlist. It records representation decisions and blocked import checks; it still cannot publish customer policy terms. Deployment/configuration boundaries, request formats and isolated Postgres test evidence are in `docs/policy-review-workflow.md`.

The subsequent capability-publication service has its own protected APIs and
publisher allowlist: see `docs/policy-publication-gate.md`. Begin with
`GET /v1/policy-publications/requirements/{draft_digest}` for exact source-note IDs
and capability requirements. Offline import previews and representation acceptance
remain insufficient for publication; a separate independent decision is required.
No real insurer source was published by these implementation checks.
