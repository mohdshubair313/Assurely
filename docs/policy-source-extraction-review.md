# Source extraction review — 2026-10-26

Three candidate packages now contain 14 extracted proposals. Every proposal has a matching quotation on a specific physical PDF page and every PDF matches its recorded SHA256. This is evidence-location validation, not human approval or a complete policy import.

| Package | Extracted proposals | Still missing |
| --- | --- | --- |
| [Care Supreme](../backend/data/source_reviews/care-supreme-candidate.json) | UIN, adult entry minimum/maximum, sum-insured options, base PED period | Variant, effective/expiry dates, full exclusions, complete premium matrix |
| [HDFC my:Optima Secure](../backend/data/source_reviews/hdfc-optima-secure-candidate.json) | UIN, adult entry minimum/maximum, base PED period | Variant, effective/expiry dates, applicable sum-insured options, full exclusions, complete premium matrix |
| [Star Comprehensive](../backend/data/source_reviews/star-comprehensive-candidate.json) | UIN, adult entry minimum/maximum, sum-insured options, base PED period | Variant, effective/expiry dates, full exclusions, complete premium matrix |

## Findings that prevent importing the old seeds

- Care's matching-UIN prospectus states lifelong adult entry, rather than the seed's 99-year cap. HDFC wording gives no maximum adult entry-age limit, rather than the seed's 65-year cap. Retain these as explicit unbounded concepts in a future normalized importer; do not create numeric sentinel ages.
- Care's benefit schedule includes options beyond the seed's sum-insured ceiling. This package preserves the listed options and flags policy-option/interpolation interpretation for review. A range alone would lose important distinctions.
- Care prospectus pages 38–39 contain Zone 1, third-year premium illustrations. Those examples are not a complete current new-business tariff and cannot validate the seed's age-band price table.
- Base PED periods retain calendar-month units and schedule/continuity conditions. An exact quoted period does not establish a particular person's remaining waiting period.
- Star's prospectus extraction contains an unrelated product/placeholder-UIN header. Physical PDF page 2 was rendered with Poppler and inspected: visible identity is Star Comprehensive with UIN SHAHLIP26044V092526 and the adult entry range. The unrelated header is not visible there. Preserve this extraction anomaly for review; no claim that all pages were visually inspected or that ingestion screening passed.

## Sources and evidence

New Care and Star prospectuses were obtained from insurer-controlled or insurer-linked URLs, then internally matched to the wording UIN. Their exact files and acquisition hashes are under `artifacts/source-audit-20261026/`. Earlier wording PDFs remain under `artifacts/source-audit-20261024/`.

- [Care prospectus](https://cms.careinsurance.com/cms/public/uploads/download_center/care-supreme---prospectus-cum-sales-literature.pdf), 39 pages, UIN CHIHLIP27061V032627.
- [Star prospectus](https://d28c6jni2fmamz.cloudfront.net/Prospectus_Star_Comprehensive_Insurance_Policy_V_12_dc6058c95e.pdf), 53 pages, relevant Comprehensive identity SHAHLIP26044V092526. Linked by the [official product page](https://www.starhealth.in/health-insurance/comprehensive-health-insurance/).
- [HDFC wording](https://customer-portal-assets.hdfcergo.com/documents/PolicyWordings_myOptimaSecure-76673175551.pdf), 69 pages, UIN HDFHLIP26058V082526.

Final evidence receipt: `artifacts/policy-source-packages-final-20261026.json`. All three packages structurally validate; all import/production flags remain false. First validation caught en-dash corruption introduced by PowerShell's pipe encoding; corrected JSON uses Unicode escapes and passed revalidation. No matching rule was weakened. Visual evidence: `artifacts/source-audit-20261026/star-prospectus-page2.png`.

Curated `*-candidate.json` files are now explicitly included by `.gitignore`; raw PDFs, runtime data and artifact captures remain excluded. No new unit tests were needed for these data-only edits; actual-file validation exercised the existing validator. The previous 18 source-contract tests remain historical.

## Next within priority 2

Follow-up: [tariff evidence review](policy-tariff-evidence-review.md) records the staged Star base grid, new HDFC prospectus and remaining tariff-rule gaps. The latest package validation receipt is `artifacts/policy-source-tariff-review-20261026.json`; the earlier receipt above remains historical.

Define the persistence contract for explicit unbounded ages, discrete cover options, period units, source-version applicability and approval bound to package digest. Continue full conditional-exclusion and tariff extraction before proposing any live import; obtain independent review of policy interpretations and calculator assumptions. Missing expiry is not open-ended validity, a product launch date is not a customer's coverage date, and a sample price is not a general rate. No database/schema/routing or frontend changes occurred. Priorities 3 and 4 remain queued.
