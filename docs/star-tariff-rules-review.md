# Star tariff conditions review - 2026-10-26

Status: evidence review candidate, not an approved quote specification. This continues priority 2 without changing runtime, schema or routing. Source: [Star Comprehensive prospectus](https://d28c6jni2fmamz.cloudfront.net/Prospectus_Star_Comprehensive_Insurance_Policy_V_12_dc6058c95e.pdf), UIN SHAHLIP26044V092526, SHA256 `0404693147bd5202e28e39bfdb8fcc87f78e7ee6aa6a6f1032f63cbec63698e1`. Pages below are physical PDF pages, including the cover. Checked on 2026-10-26; this is not a policy-effective date.

## Evidence and consequences

| Subject | Pages | Review finding and implementation constraint |
| --- | --- | --- |
| Eligibility | 2 | Adult entry 18-65 years; dependent children 91 days-25 years. Medical acceptance remains conditional. Renewal chart rows above 65 do not extend new-entry eligibility. Do not equate the chart's `3m` label with an exact 91-day eligibility boundary. |
| Zones | 3 | Five explicit geographic groups mix cities, districts and states. Named locations precede residual state areas and residual India. Preserve original names/aliases and resolve geography before lookup; missing or unrecognized location must not default to Zone E. City tier from the sizing calculator is not this tariff zone. |
| Term and payment | 2, 39 | Terms are 1/2/3 years. Second-year discount 10%, third-year 12.5%; neither is available in instalment mode. Instalment loadings are monthly 4%, quarterly 3%, half-yearly 2%, yearly 0%. Preserve grace-period, cancellation and outstanding-instalment conditions; do not multiply a discounted first-year rate by tenure. |
| Claim experience | 3-4 | Conditional renewal discount of 5% requires the stated three-year claim history and age up to 59. Floater uses eldest-member age for this discount and aggregates applicable member claims. Listed benefit claims are excluded from this calculation. Notice timing and later claim payments affect the assessment. This does not prove the tariff's general age-selection rule. |
| Wellness | 18, 24-25 | Points bands correspond to 2%, 5%, 7%, 10% discounts. Floater weights and a two-year averaging rule apply. Evidence submission deadlines and program conditions must be retained. Do not assume every applicant earns this discount. |
| PED buyback | 27-29, 53 | Optional reduction from 36 to 12 calendar months is limited to first purchase and initial chosen cover; unavailable when newly opting at renewal or on port-in. Requires medical screening and insurer acceptance. Enhanced cover and longer specified-disease waiting periods retain their conditions. First-year loadings by printed age band: 3m-35: 20%; 36-45: 30%; 46-50: 35%; above 50: 50%. This is not a recurring unconditional surcharge or blanket removal of waiting periods. |
| Add-on/channel | 29, 42 | Section I of the named Extra Protect add-on carries a stated 0.25% base-policy discount; online purchase a stated 5% discount. Separate add-on terms, applicable version, channel eligibility and combined-discount treatment require confirmation. Neither is included by default. |
| Underwriting | 41 | Risk loading is individually assessed, with stated per-condition and overall limits, communicated through a counteroffer and accepted by the proposer. Do not calculate an actual loading from diagnoses using those limits. |
| Co-payment | 38 | 10% applies to listed benefit sections where entry age is 61 or above; continuous renewals following entry before 61 retain the stated exception. This is a claim-sharing condition, not a premium discount. Current age alone cannot determine it. |

The full geographic list and selected source passages, including claim-discount exceptions, are retained in `artifacts/star-tariff-rule-evidence-20261026.json`. Fourteen passage selections passed extraction-anchor checks against the pinned PDF. The artifact is supporting evidence, not exhaustive policy interpretation or a new database contract.

## Checks performed

- Rendered physical pages 3 and 53 with Poppler and visually inspected zone grouping, conditional claim-discount text, PED loading rows and illustrative figures. The unrelated hidden extraction headers are not visible on these rendered pages; retain the existing anomaly for review.
- Reconciled seven illustrated Zone D premium figures on page 53 against the extracted base grid; **7/7 match**. Evidence: `artifacts/star-illustration-crosscheck-20261026.json`. The examples support those specific coordinates only; they do not establish a universal eldest-age pricing algorithm or full tariff accuracy.
- Revalidated the updated Star package against actual wording/prospectus bytes, hashes, page counts and field quotations. Receipt: `artifacts/star-tariff-rule-validation-20261026.json`. `premium_table` remains missing, all approvals false. The earlier three-package receipt remains historical for the previous Star package digest.
- No backend suite was rerun for these evidence-only changes. PDF rendering used a disposable container, with no application dependency changes.

## Remaining acceptance gates

Before a usable Star tariff can be approved, obtain explicit tariff age/family selection rules, location resolution and address applicability, modifier ordering/combination, rounding, applicable tax treatment, source effective-version evidence and insurer underwriting inputs. Reconcile with policy wording/schedule and qualified review. None of the staged modifiers is wired into live quotes.

Next priority-2 work: HDFC exact-variant schedule/tariff extraction, then Care complete tariff evidence and full conditional exclusions. Calculator assumption approval and unit-aware persistence remain open; flag any schema proposal before implementation. This closes the bounded Star modifier evidence pass, not priority 2 or production approval.
