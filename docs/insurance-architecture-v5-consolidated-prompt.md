# v5 — complete, self-contained prompt (not a patch)

This is a full replacement, not an addition. Paste this into a **new** Eraser document rather than "enhancing" the existing canvas — the last attempt showed that referential edits ("add these to the existing diagram") don't reliably preserve what's already there.

```
Create a system architecture diagram titled "Multi-Agent Insurance Advisory Platform (India) — v5".

Hard rule, apply everywhere: never use the words "rank", "ranking", "best", or "top" in any node label or description. Every product-facing agent uses neutral need-fit language only.

Entry (group):
"User / Family" -> "Multi-channel input: Web, mobile app, WhatsApp, voice" -> "Input validation: schema, PII scrub, abuse + injection screening" -> arrow down into Layer 1.

Layer 1 — Orchestrator Pipeline (group, labeled "Owns session state, routing, retries"):
  - Orchestrator hub: "Session state · Fan-out (Stage 2 only) · Retries + fallback"
  - Attached node beside the hub: "Rate Limiter / cost control — token + call budget per session; gates every agent call"

  Stage 1 — sequential: "Intake & Profiling Agent" — sub-label: "Multi-turn Q&A; captures age, income, dependents, city, existing cover, health flags; Human Life Value + ideal health-cover calculators; Missing Info Detector loops back (draw a self-loop arrow) until profile is complete; ends by routing Life / Health / Both via an Intent Router step".

  Stage 2 — parallel fan-out (bracket labeled "Runs concurrently — none depends on another's output"):
  - "Life Insurance Domain Agent" — "Term, endowment, ULIP — runs only if Life selected"
  - "Health Insurance Domain Agent" — "Individual, family floater, critical illness — runs only if Health selected"
  - "Risk Analysis Agent" — "Sizes coverage from risk profile — never used to rank insurers"

  Stage 3 — sequential, fan-in from Stage 2: "Compare & Verify Agent" — "Cross-checks facts across sources; Hidden Clause Detector flags fine print; Transparency Scorer rates wording openness; produces a need-fit shortlist with reasons — never a ranking"

  Stage 4 — sequential: "Guardrail & Compliance Agent" — "Blocks unlicensed-advice language, enforces IRDAI disclosure requirements, Hallucination Guard fact-checks every claim against its cited source; confidence scoring (retrieval agreement + self-consistency check) feeds the Human Advisor Escalation rule directly"

  Stage 5 — sequential: "Explanation & Report Agent" — "Generates the plain-language rationale, side-by-side comparison (need-fit framing, not ranked), and citations for every claim — rendered in the language the user used (Hindi, English, or a mix)"

  "Human Advisor Escalation" node (branch off Stage 4, labeled "low confidence OR high-stakes"): "High sum-assured, pre-existing conditions, NRI status, or low confidence — routed to a licensed advisor before delivery"

Layer 2a — Multi-Source Truth Layer (tiered by trust):
  Tier 1 "Authoritative": insurer official sites/APIs, IRDAI product filings, IRDAI performance ratios (Claim Settlement Ratio, Incurred Claims Ratio, Solvency Ratio), IRDAI Ombudsman data, Bima Sugam ("pending — once public APIs are live").
  Tier 2 "Secondary": aggregators, broker portals, market comparison feeds — price-range cross-check only, never policy wording.
  "Cross-Verification & Reconciliation" node: "Conflicts resolved in favour of the higher trust tier; disagreements recorded, not silently dropped."
  Note: "On source outage: fall back to the next trust tier; if none available, mark the fact as unverified rather than omitting it silently."

Layer 2b — Knowledge & Retrieval:
  - "Ingestion screening" — "Screens scraped pages/PDFs for embedded instructions before they enter the RAG store — treats external content as untrusted input"
  - "Policy Document RAG + Vector DB" (draw as a cylinder) — "Chunked policy wordings and brochures with citation-linked retrieval"
  - "Premium & Rules Calculator" — "Deterministic quotes and eligibility rules; no LLM-invented numbers"

Layer 2c — Trust & Safety (parallel to 2a/2b):
  - "Consent & data minimization (DPDP Act 2023)"
  - "User Profile Memory" (draw as a cylinder) — "Vector DB, consent-gated, deletable on request; stores preferences for returning users"
  - "Audit trail" — "Replayable log of what was shown, from which source, when"
  - "Conflict-of-interest disclosure" — "States plainly if any affiliate/referral revenue exists"

Layer 3 — Delivery & Feedback:
  - "Client App / Advisor Console" — "Delivers the report with disclosures, source links, and a one-click 'why am I seeing this' view"
  - "Outcome & Feedback Capture" — "Purchase, drop-off, and advisor corrections logged per case, with consent"
  - "Continuous Improvement Loop" — "Feeds prompt and guardrail tuning back into the pipeline via offline evaluation — never a live automatic change, and never framed as ranking tuning"

Cross-cutting, bottom of the diagram: "Observability — traces every stage" band, connected with dotted lines (no arrowheads) touching Layer 1, 2a, 2b, 2c, and 3. Sub-label: "Latency, cost, and outcome tracked per agent call; Guardrail catch-rate and escalation-rate monitored over time."

Below Layer 3, three blanket notes: "Every claim carries a source + last-verified date." / "Every response is generated in the language the user used (Hindi, English, or a mix)." / "Nothing in this system ranks products — only need-fit is shown."

Legend: Agent stage, Truth/data, Retrieval, Safety/human, Delivery/feedback, Observability (dotted). Keep labels short and non-overlapping. No line should cross the entire canvas.
```
