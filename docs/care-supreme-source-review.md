# Care Supreme source checkpoint - 2026-10-28

The bounded condition-evidence checkpoint is complete: a versioned extraction plan preserves 21 sections / 91 physical-page fragments from three pinned official PDFs. This is **source preparation**, not a complete tariff, approved policy import, claim-cost implementation or production approval. Priority 2 remains open.

## Sources and reproduction

| Source | Archived file | Identity |
| --- | --- | --- |
| [Policy wording](https://cms.careinsurance.com/cms/public/uploads/download_center/care-supreme---policy-terms-%26-conditions-%28effective-from-29-april-2026%29.pdf) | `artifacts/source-audit-20261024/care-supreme.pdf` | 83 pages; SHA256 `1f7647762f6c9654de6b4e28fbcb9e5f612c19c9c8756883f809176e539e01b6`; accessed October 24 |
| [Prospectus](https://cms.careinsurance.com/cms/public/uploads/download_center/care-supreme---prospectus-cum-sales-literature.pdf) | `artifacts/source-audit-20261026/care-prospectus.pdf` | 39 pages; SHA256 `b827030031d9efdc448781069f04e30c0e13c37e962f98031cfa6e046a40d90b`; accessed October 26 |
| [Revision rationale](https://selfcare.careinsurance.com/data/Care%20Supreme%20-%20Rationale%20for%20Premium%20change.pdf) | `artifacts/care-review-20261028/care-revision-rationale.pdf` | 1 page; SHA256 `d3aae5e81dba25b88c00b6563c60ac5e8a576a1b4c02ac4b03ad857618da1ffb`; accessed October 28 |

All three identify UIN `CHIHLIP27061V032627`. The new revision notice supports a **product revision** date of April 29, 2026. It does not establish an individual customer's inception date, new-business/renewal transition rules, withdrawal date or current applicability. The candidate now contains six extracted proposals and four missing fields; every field still needs review.

Run the existing offline collector with `backend/evidence_plans/care_supreme.json`; the complete command is in `backend/tools/README.md`. Existing receipts are not overwritten. Sources and outputs are ignored artifacts; the plan and candidate metadata are versioned.

Receipts:

- `artifacts/care-rule-evidence-20261028.json`: original text, page/character positions, fragment hashes, source hashes and plan hash.
- `artifacts/care-source-review-validation-20261028.json`: actual PDF/package validation.
- `artifacts/care-evidence-checks-20261028.json`: independent fragment/qualifier checks and rejection probes.
- `artifacts/care-review-20261028/care-revision-rationale-receipt.json`: download receipt for the new source.
- `artifacts/care-review-20261028/discovery-receipt.json`: archived official index, product page and public calculator response hashes.

## Evidence now preserved

All page numbers below are one-based physical PDF pages, not printed page labels.

| Area | Source pages | Preserved conditions / unresolved interpretation |
| --- | --- | --- |
| Eligibility and geography | Prospectus 1 | Age basis, family composition, seven pricing zones and adjoining-city qualifications. No address-to-zone algorithm inferred. |
| Discounts | Prospectus 1-2 | Individual-family basis, tenure, channel, NRI and other discounts, multiplicative interaction and aggregate ceiling. Conditional maximum discounts are not guaranteed rates. |
| General benefit conditions | Prospectus 2-3; wording 14-16 | Benefit dependencies, annual limits, deductible/co-payment scope, interpolation provision. No interpolation without approved endpoint rates. |
| Base benefits | Prospectus 3-6; wording 16-23 | Full benefit text and exceptions rather than unconditional short labels. |
| Optional benefits | Prospectus 6-11; wording 23-34 | All optional clauses, including room modification, waiting-period modifications, mutual exclusions, aggregate deductible, co-payments, network conditions and wellness rules. Selection requires the actual schedule. |
| Exclusions | Prospectus 11-15; wording 34-41 | Complete standard and specific blocks, waiting periods, continuity conditions and exceptions. No shortened list imported. |
| Renewal and installments | Prospectus 18; wording 46-47 | Renewal, moratorium, withdrawal, grace, unpaid-installment recovery and tenure-discount restriction. |
| Claim assessment | Prospectus 22-23; wording 57-59 | Progressive deduction and benefit-utilization orders plus payment conditions. This is evidence for a future engine, not an implemented engine. |
| Schedule and medical checks | Prospectus 23-26 | Coverage and optional-benefit schedule and pre-policy check conditions; a referenced medical-check grid must not be assumed present or complete. |
| Definitions | Wording 3-14 | Age, deductible, co-payment, room category and associated-expense qualifications. |
| Annexures | Wording 60-72 | All four non-medical lists, excluded providers with emergency qualification, and Smart Select list with its non-exhaustive/latest-list warning. These are archived lists, not a current hospital database. |
| Premium examples | Prospectus 38-39 | Complete examples and their Zone 1 / third-year restriction; no new-business tariff inferred. |

## Tariff discovery outcome and review gaps

The [official download index](https://www.careinsurance.com/health-insurance-brochure.html), [product page](https://www.careinsurance.com/product/care-supreme), exact-UIN searches, archived PDFs and [public calculator](https://abacus.careinsurance.com/religare/partner/generic-care-popup) were inspected. A full applicable rate matrix was **not established by this pass**. This does not claim that no such matrix exists.

The public calculator initially returned HTTP 406 through the web fetch tool; a normal browser-header GET succeeded and was archived. It exposes a Care Supreme selector and dynamic calculation forms. The inspected controller delegates calculations to server endpoints; it did not supply a complete downloadable tariff. No quote/purchase/contact form was submitted, no customer details were used, and no customer quote was generated. Public calculator access alone is not an approved API/data contract.

Specific unresolved items:

1. **Full pricing evidence:** matching-UIN, selected-variant rates for all applicable zone/age/family/cover/tenure coordinates, optional modifiers, tax basis, rounding and effective intervals remain required. Older UIN material and advertised daily prices are not substitutes. The prospectus refers to annexed rates, but its available final annexure contains illustrations only.
2. **Version/channel discrepancy:** the product page states adult entry age 18-99 and a narrower cover set; the pinned prospectus states lifelong adult entry and a wider schedule. Preserve both observations; do not silently select one as authoritative for an individual policy. HTML snapshots are archived with retrieval date and hashes.
3. **Provider exception reconciliation:** wording Excl11, physical page 38, limits certain emergency/accident expenses to stabilization. Annexure II, page 69, uses broader medical-emergency reimbursement language. Both passages are retained; neither becomes an unconditional full-claim promise.
4. **Claim mechanics:** prospectus section 6.6 refers to 6.1.6, and wording assessment references 3.1.1(ix). Preserve source references and resolve them before executable rules. Annual deductible state, eligible expense groups, multiple co-payment interactions, benefit-pool exhaustion and selected optional covers all need an explicit contract.
5. **Rounding:** printed family-discount figures do not establish one rounding rule from displayed base amounts. For example, 31,113 less 5% is 29,557.35 while the illustration prints 29,558; 5,046 less 5% is 4,793.70 while it prints 4,793. Hidden precision or source error is unresolved. No rounding algorithm was invented.
6. **Authenticity/applicability and approval:** exact-byte validation proves extraction consistency, not policy truth, completeness, current applicability or qualified approval. `variant`, `expiry_date`, `exclusions` and `premium_table` remain missing as usable structured fields. Import/production approval remains false.

## Validation completed

- Actual pinned-PDF hash, page-count and quoted-field validation passed for the updated candidate: six extracted proposals, four missing fields, all ten unresolved for review.
- Independently re-read all 91 fragments and checked exact text slices, contiguous declared page ranges, fragment hashes and plan hash.
- Twenty-two retained-qualifier assertions passed, including the third-year restriction, annual aggregate basis, optional-cover mutual exclusion, emergency limitations and non-exhaustive network warning.
- Eight negative probes passed: incorrect hash, incorrect page count, missing anchor, ambiguous anchor, out-of-range page, reversed bounds, duplicate section and missing source were rejected. These used the actual one-page revision PDF; they do not qualify a general PDF parser.
- Visually inspected nine rendered pages: prospectus 1/2/7/22/38/39, wording 38/69 and revision notice 1. The six multi-member printed totals reconcile; three floater figures were inspected as printed examples. This is not full-cell tariff verification or a claim-calculation test.
- No broad backend suite, model evaluation or frontend journey was run. No runtime, schema, graph routing, node or database import changed.

Rendering used `pypdfium2` and Pillow installed only under ignored `artifacts/pdf-render-runtime`; application dependencies were unchanged.

## Acceptance and next work

This checkpoint accepts **reproducible condition extraction with explicitly missing tariff evidence**. It does not accept the complete Care tariff or close release priority 2.

Next implementation checkpoint: write the shared policy-rule/import contract for Care, HDFC and Star, using these source passages and the transparency blueprint. Flag any proposed schema/routing change before implementation. Model product revision versus customer policy dates, calendar units, conditional overrides, annual deductible state, source/version provenance, authenticated review and explicit unavailable/conflicting rules. The Care tariff must remain unavailable until a matching official rate artifact or suitable insurer data contract is obtained and verified. Do not repeat the same unproductive source searches without a new lead.

Then implement the approved normalized import and complete calculator-assumption review. Auth/durable state/advisor release remain priority 3, followed by frontend integration and the complete journey at priority 4. No blueprint claim simulator or additional graph node was started in this session.
