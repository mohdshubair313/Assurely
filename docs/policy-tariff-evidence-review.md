# Tariff evidence review - 2026-10-26

Priority 2 remains open. This checkpoint stages source evidence; it does not approve policy imports or customer quotes.

## Star base annual grid

Extracted physical pages 43-52 of the archived matching-UIN Star Comprehensive prospectus into `artifacts/star-base-grid-candidate-20261026.json`. The candidate retains the document hash, physical page, zone, family code, source age-band label and nine sum-insured columns. Values are annual base premiums excluding tax.

Independent coordinate checks passed: 400 unique rows, 3,600 positive integer cells, five zones A-E, eight family groups per zone and ten age bands per group. These establish grid coverage, not correctness of every extracted cell. Poppler renders of physical pages 43 and 52 were visually inspected; four observed cells were asserted against the extracted grid:

| Zone | Family | Source age band | Sum insured (INR) | Base annual premium excluding tax (INR) |
| --- | --- | --- | --- | --- |
| A | 1A | 3m-35 | 500000 | 9849 |
| A | 1A | Above 75 | 10000000 | 132272 |
| E | 2A | 18-35 | 500000 | 11817 |
| E | 2A+3C | Above 75 | 10000000 | 371855 |

Evidence: `artifacts/extract-star-grid-20261026.py`, `artifacts/star-base-grid-coverage-20261026.json`, and `artifacts/source-audit-20261026/star-grid-page43.png` / `star-grid-page52.png`. Raw artifacts remain local and excluded from Git.

The package's `premium_table` field remains missing. Zone geography, family/age interpretation, new-entry versus renewal eligibility, optional loadings, discounts, taxes and applicability still require review. Rows above age 65 do not establish permission for new entry above the stated entry limit. Page 53 contains illustrations and PED buyback loading information; neither was silently folded into this base grid. Import approval remains false.

## Other sources and exclusions

Archived the [HDFC my:Optima Secure prospectus](https://customer-portal-assets.hdfcergo.com/documents/Prospectus_myOptimaSecure-81493430264.pdf), 291 pages, with an acquisition receipt and matching internal UIN HDFHLIP26058V082526. Physical page 60 contains eight plan columns with different cover options. The HDFC candidate now includes this source and an additional UIN quotation. Variant-specific benefits and tariffs have not been normalized or approved.

Care prospectus pages 38-39 remain illustrations, not a verified complete new-business rate matrix. A complete applicable Care tariff source is still required.

An offline page-marker inventory locates standard/specific exclusions in the wording PDFs: Care pages 34/39, HDFC 32/34, Star 31/34. `artifacts/source-evidence-inventory-20261026.json` is a navigation aid, not a complete conditional-exclusion extraction.

## Validation and next work

HDFC follow-up: [base Optima Secure variant review](hdfc-optima-secure-tariff-review.md) identifies its cover columns and six tier chart starts. Rates remain untranscribed; the package receipt is `artifacts/hdfc-optima-secure-variant-validation-20261026.json`.

Follow-up: [Star tariff conditions review](star-tariff-rules-review.md) captures the modifier evidence pass, visual checks and seven matching insurer illustration figures. Latest Star package receipt is `artifacts/star-tariff-rule-validation-20261026.json`; the earlier three-package receipt below retains the prior Star digest.

All three updated review packages passed actual-byte hash, page-count and quoted-evidence validation. Latest receipt: `artifacts/policy-source-tariff-review-20261026.json`; all human-review statuses remain pending and all import/production approval flags remain false. The previous receipt describes earlier package bytes and is retained as historical evidence.

No runtime, database schema, routing, graph node or frontend changes were made in this checkpoint. No new backend suite run is claimed for these data-only edits. Rendering used a disposable container; application dependencies were not changed.

Next, within priority 2: review Star zone/eligibility/modifier rules; extract HDFC tariffs for the exact intended variant; obtain Care's complete applicable tariff evidence; preserve full conditional exclusions. Resolve unit-aware persistence and source-version applicability before import, flagging any schema proposal first. Qualified review of policy interpretation and calculator assumptions remains necessary. Auth/state/advisor and frontend integration stay queued in the user's specified order.
