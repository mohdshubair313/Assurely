# HDFC my:Optima Secure tariff review - 2026-10-26

Status: source-backed candidate, pending human review. Source: [HDFC my:Optima Secure prospectus](https://customer-portal-assets.hdfcergo.com/documents/Prospectus_myOptimaSecure-81493430264.pdf), 291 pages, UIN HDFHLIP26058V082526, SHA256 recorded in `artifacts/source-audit-20261026/hdfc-prospectus-receipt.json`.

## Base variant identified

Physical PDF page 69 identifies the distinct **Optima Secure Plan** rate chart and lists these discrete base sum-insured columns: ₹5L, ₹10L, ₹15L, ₹20L, ₹25L, ₹50L, ₹1Cr and ₹2Cr. These values are staged in the HDFC candidate package with the matching page quote. Other plan variants have separate tables and must not be combined with this one.

The base plan has six geographic-tier chart starts on physical pages 69, 73, 77, 81, 85 and 89 (each tier's chart continues across four pages, through page 92). The chart uses age rows 0-89 plus a `>=90` row. Those source labels do not by themselves establish the policy's exact age calculation date or eligibility conditions. The base chart is headed “Gross Premium”; tax, rating basis and all applicable adjustments require reconciliation with the full prospectus and schedule.

Other chart blocks in this same prospectus include Optima Super Secure (93-116), Global (117-140), Global Plus (141-164), Lite (165-188), Select (189-212), Secure+ (213-236), and separately priced optional covers. These page ranges identify where rate charts begin and end; each has distinct geography/coverage structure and none is represented by the base-plan candidate.

## Current implementation state

- Extracted the six base-plan tiers to `artifacts/hdfc-optima-secure-base-grid-candidate-20261026.json`: **546 rows / 4,368 premium cells**, with each row linked to a physical PDF page. Coordinate coverage is six tiers × 91 age rows × eight cover columns. Values remain printed gross premium values; they were not normalized for tax or adjustments.
- Rendered and inspected physical pages 69, 72, 89 and 92. Four boundary cells across Tier 1 and Tier 6 match the extracted values. This is a targeted visual check, not a full cell-by-cell review.
- `artifacts/hdfc-optima-secure-chart-map-20261026.json` records the source hash, chart pages, coverage and remaining limitations.
- `artifacts/hdfc-optima-secure-variant-validation-20261026.json` records actual PDF hash/page/quote validation. The package is structurally valid; effective/expiry dates, full exclusions and production-usable premium table remain unresolved. Human/import/production approvals remain false.
- Extraction and staging scripts: `artifacts/extract-hdfc-optima-secure-grid-20261026.py` and `artifacts/stage-hdfc-optima-secure-variant-20261026.py`.

## October 27 implementation follow-up

Added reusable commands in `backend/tools/` and a pinned extraction plan in `backend/evidence_plans/hdfc_optima_secure.json`. The collector saved ten sections / 28 physical-page fragments, including complete exclusion blocks from both documents and the Protect Benefit override. Exact anchors, hashes and page counts are checked during extraction; interpretation is still pending.

Source findings (physical pages, checked 2026-10-27):

| Evidence | Consequence for implementation |
| --- | --- |
| Wording page 8, definition 2 | Use completed years at last birthday at inception of the relevant policy year; do not use today's age for all years. |
| Prospectus page 50, section 14 | Rating uses city of residence supplied in the proposal. Complete six-tier geography is available; address resolution remains to implement. |
| Prospectus pages 53-54, section 16 | Eldest member pays the age-specific full rate; additional members have a 55% floater discount. Discount order and rounding still require reconciliation. |
| Prospectus pages 29-31 | Preserve channel, employee, loyalty, family, tenure, NRI, lifetime and deductible conditions. The 20% cap applies to the four explicitly listed discounts, not automatically every modifier. NRI requires declaration and return/differential-payment conditions; it is independent of escalation logic. |
| Prospectus pages 49-53 | Preserve counteroffer/underwriting conditions and claims-history tables, including individual age exceptions. Source table layout remains unnormalized. |
| Wording pages 30-35 and prospectus pages 31-36 | Full exclusion blocks retained, including accident/continuity and benefit exceptions; not converted into unconditional exclusions. |
| Wording pages 16-17 | Protect Benefit references C.2 Specific Exclusions, while the actual heading is C.3. The discrepancy is retained for review instead of silently repaired. |

Fixed a concrete extraction defect: the previous single-line heading capture truncated Tier 5 geography. The new extractor retains wrapped headings, including the Haryana and West Bengal areas. All 4,368 price values match the earlier grid. Age labels and raw row text remain preserved; the output uses the source label `gross_premium_inr` without assuming tax composition.

Current artifacts: `artifacts/hdfc-rule-evidence-20261027.json`, `artifacts/hdfc-base-grid-20261027.json`, and `artifacts/hdfc-source-review-validation-20261027.json`. The older artifacts remain historical. Candidate metadata no longer says the tariff is untranscribed. Qualified approval, effective/expiry applicability, tax treatment, rounding and modifier composition remain open; these outputs are not a quote engine. The contract-level exclusion field also remains missing until normalized interpretation is reviewed.

Tool usage and validation limits: [offline commands](../backend/tools/README.md). Docker was unavailable; local backend Python handled extraction without application startup. Targeted lint passed; no unit/integration suite was run. Next source task is Care complete tariff discovery and condition extraction using the reusable collector, followed by the outstanding normalized import and calculator review work. No database schema, routing or graph-node change occurred.
