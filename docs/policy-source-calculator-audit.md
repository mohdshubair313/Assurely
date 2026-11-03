# Policy source and calculator audit

Accessed 2026-10-24. Engineering source audit, not insurer confirmation or underwriting approval. No live records were replaced. The second completion gate remains open.

**2026-10-25 follow-up:** The Care download blocker below is resolved. Following the official index's exact PDF link with standard PDF request headers retrieved an 83-page document, internal UIN CHIHLIP27061V032627. Bytes and hash are archived in `artifacts/source-audit-20261024/care-receipt.json`. The initial candidate package passed actual-file hash/page/quote validation; approval remains false. See [review contract and remaining fields](policy-source-review-contract.md). Historical retrieval failures below are retained as audit history.

## Source identity

| Product | Primary evidence | Finding / import decision |
| --- | --- | --- |
| HDFC ERGO my:Optima Secure | [Insurer wording](https://customer-portal-assets.hdfcergo.com/documents/PolicyWordings_myOptimaSecure-76673175551.pdf), UIN HDFHLIP26058V082526 | Archived exact bytes. Printed pages 30–31 specify 36 months with schedule/continuity conditions; optional reductions appear on page 26. A generic 1,095-day value loses these conditions. Seed not approved. |
| Star Comprehensive | [Official product page](https://www.starhealth.in/health-insurance/comprehensive-health-insurance/) links [policy PDF](https://d28c6jni2fmamz.cloudfront.net/Policy_Star_Comprehensive_Insurance_Policy_V_21_3a414ab104.pdf), UIN SHAHLIP26044V092526 | Archived exact bytes. Filename contains V21 but internal wording identifies V24/2025; use document contents for identity. PED period has continuity conditions and an optional reduction. Full premium/exclusion/variant import remains unapproved. |
| Care Supreme | [Official download index](https://www.careinsurance.com/other-downloads.html) lists wording effective 29 April 2026 | Current PDF retrieval failed through web fetch; direct index retrieval returned HTTP403. Older searchable CHIHLIP23128V012223 wording cannot be substituted as current. Exact-byte validation remains open. |

HDFC and Star files and hashes: `artifacts/source-audit-20261024/manifest.json`. Access dates do not establish effective dates or approval. Seed hashes derive from invented version strings rather than document bytes, and January 2024 effective dates are unverified. All seed premium rows remain unverified; no model-generated replacements were used.

## Calculator findings

| Existing assumption | Decision |
| --- | --- |
| Annual medical inflation 14%; five-year projection | Unverified development scenario. [Aon's India release](https://proxypass.aon.com.au/apac/in-the-press/asia-newsroom/2025/india-outpaces-global-average-with-2026-medical-trend-at-11-5-percent-aon-reports) projects 11.5% for employee medical-plan costs in 2026. That population/forecast is not a universal retail-family estimate; replacing the constant would not validate this calculator. |
| Tertiary thresholds INR 15L/10L | No supporting source established. Requires defined treatment basket, geography, cost evidence and qualified review. |
| City bases INR 10L/7.5L/5L, dependent increment INR 2.5L, age multipliers 1/1.25/1.5, PED buffer and floor INR 5L | Unverified heuristics. Deterministic arithmetic does not establish suitability. |
| Universal statutory 36-month PED period | Removed. Profile-only output is now unknown (`None`); selected policy/schedule, options and continuity credits must establish the actual period. |
| Sufficient sum insured guarantees room eligibility without deductions | Removed. Policy wording/schedule must establish eligibility and deductions; amount alone cannot do so. |

Both calculators return `assumptions_status=unverified_development_only`. This metadata is not itself a delivery control. Numeric scenarios/arithmetic remain unchanged. Deviation #5 applies to all these assumptions, not just inflation and tertiary thresholds.

## Schema issue flagged before migration

`policy_terms.waiting_period_days_preexisting` cannot faithfully represent calendar-month periods as 1,095 days. Tables also lack explicit UIN/variant identity and reviewed-source approval state. These require a deliberate schema/import contract before verified data promotion. No migration or routing change occurred.

Next within priority 2: acquire current Care wording; define import fields for UIN/variant, period units/conditions, source hash and approval provenance; extract/review every required term and applicable premium input. Qualified review of policy data and calculator assumptions remains necessary. Priorities 3 and 4 remain queued; this audit is not source approval or production readiness.
