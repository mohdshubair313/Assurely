# Assurely — Product Design README

> **A calm, explainable insurance companion** that helps people understand health insurance first, choose with confidence, and expand to life insurance when the product roadmap is ready.

**Design status:** Product/UI specification  
**Primary platform:** Responsive web application  
**Core v1:** Web chat + health insurance comparison  
**Planned v2:** Life insurance guidance, WhatsApp, multilingual/voice, family access, renewals, policy upload

---

## 1. Design thesis

Insurance is usually presented at the worst possible moment: when a person is worried, short on time, and unable to decode terms such as *waiting period*, *co-pay*, *sub-limit*, or *sum insured*.

The interface should not make people feel like they are being sold to. It should make them feel **oriented**.

### The experience promise

1. **Start with a human situation, not a policy catalog.**
2. **Ask only for information that changes the recommendation.**
3. **Show trade-offs before asking for a choice.**
4. **Separate verified facts from AI explanations.**
5. **Never hide uncertainty, exclusions, or a need for human help.**

The visual language is intentionally *not* “generic AI SaaS”: no purple gradients, glowing robot imagery, or black-glass dashboard clichés. Instead, it combines **sky blue clarity**, **warm cream reassurance**, **ink-like text**, and **quiet kinetic details**.

---

## 2. Product framing

### Brand concept

**Working name:** `Assurely`  
**Tagline:** *Understand your cover before life asks for it.*

Alternative names if needed:
- Coverwise
- PlainCover
- NurturePlan
- SurePath

### Tone of voice

| Do | Avoid |
|---|---|
| “Here’s what this plan covers—and where it may fall short.” | “Best plan guaranteed.” |
| “Based on what you shared…” | “Our AI knows what’s right for you.” |
| “You can compare this before deciding.” | “Buy now before it’s too late.” |
| “A licensed expert can help with this question.” | “This is legal/medical/financial advice.” |

**Voice traits:** clear, measured, warm, specific, non-alarmist, never patronizing.

---

## 3. The real problem to visualize

The landing page should make the invisible friction of insurance visible in under five seconds.

### Recommended hero visual: **“The Coverage Gap” — a 3D kinetic diorama**

Create a soft, editorial 3D scene of a small cream-colored home on a floating circular map. Around it sit calm, recognizable life objects:

- a child’s backpack
- a parent/elder-care medicine organizer
- a small hospital document folder
- a salary/payday card
- a policy document with folded, unreadable fine print

A translucent **sky-blue protective canopy** begins as fragmented glass panels. As the visitor scrolls or completes a sample question, the panels gently align into one complete cover over the home. Two small gaps remain visible and label themselves **“waiting period”** and **“room-rent limit”**—showing that insurance is not simply “covered” or “not covered.”

#### Why this is the right metaphor

- It shows the real emotional job: protecting a household, not shopping for a PDF.
- It makes exclusions and policy conditions tangible without fear-based visuals.
- It supports health insurance in v1, while naturally extending to life insurance in v2.
- It gives the product a distinctive, ownable motion moment.

#### Motion behavior

- **Idle:** gentle 4–6 second parallax drift; sunlight/shadow slowly shifts; document edge moves slightly.
- **On scroll:** fragmented coverage panels ease into position using a spring-like settle (not a dramatic explosion).
- **On hover/focus:** hover labels reveal a plain-English example for a gap.
- **Reduced motion:** render the final assembled canopy as a static illustration; no auto-animation.

**Do not use:** a spinning 3D object, aggressive particle effects, flashing medical symbols, or constant looping animations that compete with reading.

### Image / visual direction

For imagery inspired by Imageory’s collection, choose a **Blue-cosmos / gradients-style abstract sky visual** as the background atmosphere for the hero—not as a literal stock photograph. It should be used as a slow-moving, masked canvas texture behind the 3D diorama: pale cloud-blue, icy cyan, soft cream, and a little muted teal. Imageory’s visible categories include *Blue-cosmos*, *Gradients*, *Ethernal-flow*, *Abstract-landscape*, and *Surreal*; **Blue-cosmos + Gradients** best supports the product’s calm, protective, modern character. citeturn0view1

### Secondary visuals

- **Policy anatomy cards:** beautifully simplified document fragments with highlighted clauses.
- **Decision-path timeline:** line-art route from “Your life” → “What matters” → “Compare” → “Understand gaps” → “Choose / talk to expert.”
- **Trust ledger:** structured, timestamp-like proof cards for *source*, *policy version*, *assumptions*, and *why this recommendation changed.*
- **Scenario mini-scenes:** illustrated modules for young family, self-employed adult, caregivers, and chronic-condition planning; each should be represented respectfully, never stereotypically.

---

## 4. Visual system

### Color system

The palette should feel like a trustworthy service desk in daylight: cool enough for clarity, warm enough for empathy.

| Token | Light mode | Dark mode | Use |
|---|---:|---:|---|
| `--canvas` | `#F8F5ED` warm cream | `#0E1C24` deep blue-black | App background |
| `--surface` | `#FFFDF8` | `#142733` | Cards, sheets, inputs |
| `--surface-raised` | `#FFFFFF` | `#19313E` | Elevated modules |
| `--ink` | `#14242F` | `#EEF7F8` | Primary copy |
| `--ink-muted` | `#5C6A70` | `#AABCC1` | Secondary copy |
| `--sky` | `#5BA9D8` | `#78C4EF` | Primary action / links |
| `--sky-strong` | `#187CB8` | `#9AD8F5` | Hover / emphasis |
| `--teal` | `#187B78` | `#70D2C9` | Confirmed / verified states |
| `--sand` | `#F0DFC0` | `#3D3528` | Warm accent / tags |
| `--amber` | `#B96A18` | `#FFC36E` | Attention / caveat |
| `--coral` | `#BC5D54` | `#FF9C91` | High-risk / error, used sparingly |
| `--line` | `#DCE4E1` | `#2B4653` | Borders / dividers |

#### Rules

- Blue is for **progress and action**, not every decoration.
- Teal is for **verified evidence**, not “success” confetti.
- Amber flags **important trade-offs**, never panic.
- Reserve coral for errors, critical coverage gaps, or urgent escalation.
- Avoid pure black and pure white; cream and deep blue-black retain warmth.

### Typography

Use different font roles rather than one “brand font” everywhere.

| Role | Font | Why | Typical usage |
|---|---|---|---|
| Display | **DM Serif Display** | Human, editorial, reassuring—not corporate | Hero headlines, key reflective statements |
| UI / body | **Manrope** | Clean, highly legible, contemporary | Navigation, forms, paragraphs, cards |
| Evidence / data | **IBM Plex Mono** | Signals precision and provenance | Clause IDs, timestamps, comparison numbers, source labels |

**Fallback stack:** `Georgia, ui-serif` / `Inter, system-ui, sans-serif` / `ui-monospace, SFMono-Regular, Menlo, monospace`.

#### Type scale

- Hero: `clamp(3rem, 6vw, 5.7rem)`, DM Serif Display, 0.96 line-height
- Section title: `clamp(2rem, 3.5vw, 3.5rem)`, DM Serif Display
- H3: 24–28px, Manrope 650
- Body: 16–18px, Manrope 450–500, 1.55–1.7 line-height
- Labels/meta: 12–13px, IBM Plex Mono, uppercase only when necessary

### Shape, spacing, and texture

- **Grid:** 12 columns desktop, 6 tablet, 4 mobile.
- **Max content width:** 1240px; reading width: 680px.
- **Radius:** 14px inputs, 20px cards, 28px hero panels—avoid overly pill-shaped interfaces.
- **Borders:** thin, cool-gray/teal-tinted; subtle paper grain in backgrounds only.
- **Shadows:** broad, low-opacity blue-gray shadows; never neon glow.
- **Icons:** 1.75px rounded line icons with occasional filled emphasis.

---

## 5. Interaction and motion principles

The design should follow a practical motion philosophy: motion must establish hierarchy, continuity, feedback, or spatial understanding—not decorate empty space. The inspiration source explicitly focuses on UI animation selection, review, improvement, and identifying where motion is genuinely useful. citeturn0view0

### Motion tokens

| Situation | Duration | Easing | Notes |
|---|---:|---|---|
| Hover/focus | 120–160ms | ease-out | Color, 1–2px lift max |
| Button press | 90ms | ease-in | Slight scale to 0.98, no bounce |
| Card enter | 220–280ms | cubic-bezier(.2,.8,.2,1) | Opacity + 8px translate |
| Panel / dialog | 260–340ms | spring-like | Preserve origin context |
| Step transition | 300–420ms | cubic-bezier(.22,1,.36,1) | Crossfade plus directional slide |
| Hero 3D idle | 4–6s loop | sine-like | Low amplitude only |

### Rules for useful animation

- Animate **one principal thing per viewport**.
- Never animate financial/coverage numbers in a way that looks like they are changing unpredictably.
- Use skeletons only for genuinely loading content; otherwise show a concise status explanation.
- Respect `prefers-reduced-motion` globally.
- Keep chat streaming readable: cursor pulse is enough; avoid repeated typing effects.

---

## 6. Information architecture

The product has two connected layers:

1. **Public confidence layer** — explains the mission, builds trust, and lets a visitor begin.
2. **Private decision workspace** — collects consented context, compares policy terms, records reasoning, and supports escalation.

```text
PUBLIC
Home / Landing
 ├── How it works
 ├── What we compare
 ├── Trust & safety
 ├── FAQ
 ├── Sign in
 └── Start assessment

AUTHENTICATED WORKSPACE
Onboarding & consent
 ├── Intake conversation
 ├── Your priorities
 ├── Compare plans
 ├── Recommendation / explanation report
 ├── Ask a follow-up
 ├── Save / return later
 ├── Human expert escalation
 └── Account & privacy controls

OPERATIONS (internal)
Admin sign-in
 ├── Policy terms management
 ├── Document ingestion review
 ├── Escalation queue
 ├── Decision trace viewer
 ├── Feedback validation queue
 ├── Evaluation dashboard
 └── Audit / consent records
```

---

## 7. Full customer journey and page flow

### Primary visitor flow

```text
Landing page
  → “Find my cover”
  → Sign up / sign in
  → Consent and privacy choice
  → Quick intake (chat + structured chips)
  → Missing-information loop, if needed
  → Personal priorities summary
  → Compare eligible plans
  → Plan detail / plain-English clause explanation
  → Recommendation report
      ├→ Save comparison
      ├→ Ask another question
      ├→ Speak to an expert
      └→ Start over / edit assumptions
```

### Returning-user flow

```text
Sign in
  → Home workspace
  → Resume unfinished comparison OR view saved report
  → Change life details / goals
  → Re-run comparison
  → See “What changed and why”
  → Save new version
```

### Safety / uncertainty flow

```text
User asks high-stakes, ambiguous, or unsupported question
  → Answer identifies limitation
  → “I can explain the policy wording, but not replace licensed advice.”
  → Present verified source / clause if available
  → Offer expert escalation
  → Hold final purchase-oriented output when escalation is required
```

### Technical product flow aligned to the roadmap

The UI should mirror the backend’s deterministic workflow rather than pretending an LLM is a black-box advisor.

```text
User message
  → input validation
  → missing-info detector
      ├→ request only the next necessary answer
      └→ continue
  → intent router (health in v1; life later)
  → health domain analysis + risk analysis (parallel)
  → deterministic policy-term verification + clause RAG wording
  → guardrail decision
      ├→ approved: explanation report
      └→ escalation: delivery hold + human-help route
  → persist consent, decision trace, audit log, and optional memory
```

**Important scope signal in the UI:** v1 must say **“Health insurance guidance”** everywhere product-specific decisions happen. Do not tease a fake Life Insurance workspace before it exists. Introduce life as a calm, honest “coming next” item only on the public roadmap or waitlist—not a disabled core feature.

---

## 8. Page-by-page design specification

## 8.1 Landing page (`/`)

### Job

Turn anxiety and confusion into enough confidence to begin a short, low-pressure assessment.

### Layout

1. **Announcement strip**
   - “Health insurance guidance, explained in plain language.”
   - Small `Verified policy terms` evidence indicator.

2. **Navigation**
   - Logo / wordmark: Assurely
   - How it works · What we compare · Trust · FAQ
   - `Sign in` text action
   - `Find my cover` primary CTA

3. **Hero — 70/30 editorial split**
   - Left: headline, subhead, CTA pair
   - Right: the 3D “Coverage Gap” diorama
   - Headline:
     > Insurance shouldn’t make you guess what your family is covered for.
   - Supporting line:
     > Tell us what matters. We translate policy terms, compare the trade-offs, and show exactly what to ask before you decide.
   - Primary CTA: `Find my cover`
   - Secondary CTA: `See how comparisons work`
   - Microcopy: “Takes about 5 minutes · No pressure to buy”

4. **Social-proof alternative (do not use unverified testimonials)**
   - Use a product truth strip instead:
   - “Built to show: exclusions · waiting periods · room limits · co-pay · evidence sources”

5. **Problem → clarity narrative**
   - Before: a messy policy document with scattered sticky notes.
   - After: a guided comparison showing what matters to *this* household.

6. **How it works — 3 steps**
   - `1. Tell us your priorities`
   - `2. Compare the terms that change the outcome`
   - `3. Decide with a clear explanation—or ask an expert`

7. **Interactive clause explainer**
   - A faux policy excerpt with highlighted phrases.
   - Clicking “Room rent limit” reveals a 60-word plain explanation and a “why it matters” example.

8. **Scenario cards**
   - Young family · Self-employed · Caring for parents · Planning around an existing condition
   - Cards route to pre-filled, editable demo conversations.

9. **Trust / provenance section**
   - “Every recommendation has a trail.”
   - Show source, plan version, facts used, missing information, and review status.

10. **Final CTA**
    - Cream background with blue paper-cut canopy motif.
    - “Bring your questions. Leave with clearer ones.”

11. **Footer**
    - Help / privacy / consent / terms / accessibility / contact
    - Avoid fake insurance-carrier logos.

### Landing-page responsive behavior

- On mobile: hero copy first, 3D scene second at 4:3; sticky bottom `Find my cover` CTA.
- Collapse main nav into a menu, but preserve visible sign-in.
- Avoid more than 2 cards horizontally on tablet and 1 on mobile.

---

## 8.2 Authentication (`/sign-in`, `/sign-up`, `/verify`)

### Job

Make account creation feel like a privacy checkpoint, not a sales funnel.

### Design

- Split-screen desktop: warm cream content side + small framed version of the protective-canopy scene.
- Sign-in panel with generous whitespace and a precise title: `Continue your insurance workspace`.
- Support magic link / email + password / approved SSO according to the actual implementation.
- Use a visible security note beneath form controls:
  - “We ask permission before storing information used in your comparison.”
- Never include a broad marketing consent checkbox preselected.

### Error states

- Inline field errors with clear recovery text.
- Authentication failure should never disclose whether an email account exists unless security policy permits it.

---

## 8.3 Consent and profile start (`/onboarding/consent`)

### Job

Gain informed consent before sensitive data is used or retained.

### Layout

- Progress indicator: `Step 1 of 4`.
- A short statement in plain language:
  > To compare plans for your situation, we may use the details you choose to share. You control whether we save them for later.
- Separate toggles/choices:
  - Required: process information for this comparison
  - Optional: save profile for future comparisons
  - Optional: receive updates
- “What we store / What we don’t” expandable panel.
- Link to `Download or delete your data` settings after account creation.

### Trust detail

Show consent as a durable receipt: date, scope, and revoke action—matching the roadmap’s `consent_records` requirement.

---

## 8.4 Guided intake (`/assessment`)

### Job

Collect only material decision inputs without making the user fill in a cold, long insurance form.

### Layout

- Main area: conversational thread (60%)
- Side area: “Your answer map” (40%) on desktop, bottom sheet on mobile
- Prompt cards combine conversational copy with quick-select chips and an optional free-text field.

### Example sequence for v1 health insurance

1. Who needs cover? (self / partner / children / parents)
2. Where do you live / need treatment access?
3. Preferred yearly budget range?
4. What matters most? (large hospital network, lower out-of-pocket cost, maternity, chronic-care relevance, flexibility)
5. Any existing coverage or conditions you want considered? (optional, sensitive-data notice)
6. Anything else you want us to prioritize?

### Missing-info loop UI

If the backend’s `needs_intake` state is true:

- Ask one question at a time.
- Explain why it matters: `We ask this because room limits can affect your out-of-pocket cost.`
- Include `I’m not sure` and `Skip for now` when valid.
- Do not visually reset the conversation; preserve answers and show editable summaries.

### Progress language

Use “You’re building a clearer comparison” rather than percent-only gamification.

---

## 8.5 Priorities checkpoint (`/assessment/priorities`)

### Job

Prevent a recommendation from appearing before the user can verify the assumptions.

### Layout

- Heading: `Here’s what we’ll optimize for.`
- Priority chips ordered by importance.
- Assumption cards:
  - Household: 2 adults + 1 child
  - Budget: moderate
  - Preference: broad cashless network
  - Unknown: current policy details not provided
- Each card has `Edit`.
- CTA: `Compare plans using these priorities`

This checkpoint directly supports decision provenance: the final report must show the same inputs.

---

## 8.6 Compare plans (`/compare`)

### Job

Help people compare consequences, not just premium numbers.

### Layout

- Sticky comparison header with plan selector (up to 3 plans).
- First row: “Best for your priorities” summary—not a winner badge.
- Comparison categories in this order:
  1. Overall fit for your stated priorities
  2. Estimated cost / premium context
  3. Hospital / network relevance
  4. Waiting periods
  5. Room-rent or treatment sub-limits
  6. Co-pay / out-of-pocket mechanics
  7. Pre-existing-condition treatment rules
  8. Key exclusions and uncertainty
  9. Evidence / policy clause source

### Data presentation rules

- Use plain-language label + exact policy wording toggle.
- Mark fields as `Verified`, `Needs review`, or `Not found in available documents`.
- Never make a policy “green” simply because it is cheaper.
- Use a neutral comparative bar or table, not a gamified score gauge.
- Any calculated score must reveal its inputs and weighting.

### Key CTA choices

- `Read why this fits`
- `Compare another plan`
- `Talk to an expert`

---

## 8.7 Plan detail / policy clause view (`/compare/:planId`)

### Job

Make policy evidence understandable and inspectable.

### Layout

- Summary header: plan name, policy version/date, source availability.
- Two-column desktop:
  - left: plain-English explanation
  - right: original clause snippets with source page / section references
- “What this could mean in real life” examples should be explicitly labeled as examples, not promises.
- “Questions to ask before choosing” section generated from known gaps.

### Evidence UI

Use IBM Plex Mono for source metadata:

```text
SOURCE  Policy wording v2026.04
CLAUSE  Section 5.2 · page 17
STATUS  Verified against stored policy terms
```

---

## 8.8 Recommendation report (`/report/:id`)

### Job

Deliver a decision-ready explanation with guardrails and a permanent audit trail.

### Page sections

1. **Outcome summary**
   - “Based on your priorities, Plan A appears to be the closest fit.”
   - Follow immediately with the limitations.

2. **Why it matches**
   - 3–5 bullets tied to stated priorities.

3. **Trade-offs to accept consciously**
   - Waiting period, exclusions, co-pay, premium, network limitation.

4. **What could change this recommendation**
   - Missing/changed details, updated policy wording, eligibility outcome.

5. **Evidence drawer**
   - Inputs used, policy terms checked, timestamp, source versions.

6. **Next best action**
   - Compare again · Save report · Ask an expert

7. **Safety / escalation module when required**
   - “This needs a licensed human review before we can make a final recommendation.”
   - Explain why, preserve user progress, and provide the handoff path.

### Report visual hierarchy

Use a calm “briefing document” aesthetic—not dashboard clutter. The result should feel saveable and printable, with card sections but strong editorial rhythm.

---

## 8.9 Ask follow-up (`/report/:id/chat`)

### Job

Allow natural questions while keeping the report and evidence context visible.

### Layout

- Threaded chat left; compact report facts and source drawer right.
- Suggested prompts:
  - “Explain the waiting period simply”
  - “What could I pay myself?”
  - “Show the source for this”
  - “What should I ask an agent?”
- Stream responses in chunks with clear citations/source blocks.
- If uncertain, show `I couldn’t verify this from the policy terms we have` instead of fluent guessing.

---

## 8.10 Human expert escalation (`/expert-help`)

### Job

Make escalation feel like continuity of care, not a dead end.

### Layout

- Confirm what is being shared with the expert.
- Let the user select urgency / preferred contact method where supported.
- Generate a compact handoff summary:
  - user priorities
  - plans compared
  - unresolved questions
  - audit/report ID
- Status timeline: `Requested` → `Assigned` → `In review` → `Follow-up received`.

### Guardrail behavior

When the system is in delivery-hold status, the UI must not show a persuasive “buy this plan” CTA. It should only offer review, clarify assumptions, or wait for the expert outcome.

---

## 8.11 Workspace home (`/app`)

### Job

Give returning users a calm place to resume, rather than an empty dashboard.

### Modules

- Resume latest assessment
- Saved reports
- “What changed since your last comparison?”
- Consent / data controls
- Help and expert requests

Use a timeline rather than generic analytics charts. This product’s primary value is decisions, not daily engagement.

---

## 8.12 Account, privacy, and data controls (`/settings`)

### Required sections

- Profile / household information
- Stored comparison data
- Consent history and revoke controls
- Export data
- Delete account/data request
- Communication preferences
- Security / sessions

Every personal-data page needs clear consequences: e.g., “Deleting saved profile information will not erase legally required audit records where retention applies.” Actual wording must be reviewed for the operating jurisdiction.

---

## 8.13 Internal operations console (`/ops`)

### Pages aligned to the roadmap

| Page | Purpose |
|---|---|
| `Policy terms` | Manage structured terms and source documents |
| `Ingestion review` | Screen scraped/uploaded content before RAG indexing |
| `Escalations` | Review held cases and continue human handoff |
| `Decision traces` | Inspect inputs, node outputs, source evidence, guardrail decision |
| `Feedback validation` | Review user feedback before it becomes training/eval material |
| `Evaluation dashboard` | Track pass/fail cases, retrieval vs generation metrics, credibility score |
| `Audit log` | Immutable operational history |

### Ops design

- Dense but readable: data table first, detail drawer second.
- Use color only for status; never color-code meaning without text.
- Make sensitive fields masked by default.
- Decision trace view should look like a legible timeline, not raw JSON—while retaining a raw JSON tab for engineers.

---

## 9. Design system component inventory

### Foundation

- `AppShell`
- `TopNav`
- `Footer`
- `SectionContainer`
- `PaperSurface`
- `StatusPill`
- `EvidenceLabel`
- `SourceReference`
- `ProgressPath`

### Input / onboarding

- `ConversationalPrompt`
- `ChoiceChip`
- `PriorityRanker`
- `SensitiveInfoNotice`
- `InlineWhyWeAsk`
- `AnswerSummaryCard`
- `ConsentReceipt`

### Comparison / explanation

- `PlanCompareTable`
- `TradeoffCard`
- `ClauseExplainer`
- `PolicySourceDrawer`
- `VerifiedFact`
- `UncertaintyNotice`
- `QuestionToAskCard`
- `DecisionTraceSummary`

### Safety / support

- `EscalationBanner`
- `ExpertHandoffSummary`
- `DeliveryHoldState`
- `DataControlPanel`

### Motion / visual

- `CoverageGapScene`
- `CoveragePanel`
- `PolicyPaperStack`
- `ScrollReveal` (used sparingly)

---

## 10. States that must be designed, not deferred

Every core page needs explicit states for:

- Loading / streaming
- Empty
- Partial data
- No matching plans
- Source unavailable
- Source conflict
- Guardrail hold
- Expert escalation requested
- Session expired
- Network failure
- Permission denied
- Reduced motion
- Keyboard-only focus

### Example: no matching plans

Do not say “No results.”

> We couldn’t find a plan that meets all of the priorities you selected from the policies currently available. You can widen a preference, compare trade-offs, or ask an expert to review your situation.

Actions: `Adjust priorities` · `Ask an expert` · `Save this search`

---

## 11. Accessibility and inclusive design

- Meet **WCAG 2.2 AA** contrast and focus requirements.
- Never rely on hue alone for verified/caution/error status.
- All comparison tables require a responsive alternative: stacked plan cards with a category selector.
- Keep body text at 16px minimum; support browser zoom to 200% without loss of content/functionality.
- Provide reduced motion, keyboard-accessible drawers/dialogs, and semantic headings.
- Use plain language; define insurance terms in place.
- Do not use fear-inducing imagery around illness, death, disability, or debt.
- Support screen-reader summaries for data comparisons: “Plan A has a 2-year waiting period; Plan B has 3 years.”

---

## 12. Content rules for an insurance decision product

### Always show

- What information was used
- What terms were verified
- What terms were not verified
- Important exclusions or waiting periods
- Assumptions and uncertainty
- An expert route where required

### Never imply

- Guaranteed claim approval
- Universal “best plan” status
- Legal, medical, or licensed-financial advice beyond the product’s allowed scope
- That an uploaded/source policy is current unless version/date verification confirms it

### Recommended labels

- `Verified against policy terms`
- `Explanation generated from verified terms`
- `Needs human review`
- `Policy wording not available`
- `Based on the priorities you shared`

---

## 13. Build sequencing: map the UI to the technical roadmap

| Roadmap phase | UX delivered | UX intentionally deferred |
|---|---|---|
| Phase 0 | Design tokens, auth shell, consent receipt pattern, empty/report states, evaluator/ops skeleton | Polished 3D production scene |
| Phase 1 | Landing, web chat intake, health-only compare, report, policy evidence view | WhatsApp, life, multilingual, voice |
| Phase 2 | Escalation, decision-trace summary, source status, feedback controls | Public transparency center |
| Phase 3 | “Why did this change?” comparison versions, credibility indicator for internal use | Automated persuasion/personalization |
| Phase 4 | Mobile web refinement and channel-aware handoff patterns | Full multi-channel redesign |
| Phase 5 | Life-insurance flow, family space, renewal views, policy upload | Only after corresponding evaluation coverage exists |

---

## 14. Suggested implementation approach

### Front end

- **Framework:** Next.js / React + TypeScript
- **Styling:** CSS variables + Tailwind or CSS Modules; token-first architecture
- **Animation:** Framer Motion / Motion One for interface transitions; React Three Fiber only for the hero scene if performance budget allows
- **Icons:** Lucide-style line icon set
- **Charts:** Avoid default chart libraries in the consumer flow; use bespoke comparison bars/tables. Use chart libraries only in ops analytics.

### Performance budget

- Landing LCP target: under 2.5 seconds on a mid-tier mobile connection.
- 3D hero should progressively enhance:
  1. static poster image default,
  2. lightweight CSS/parallax version,
  3. WebGL only on capable devices.
- Lazy-load non-essential visuals below the fold.
- The initial assessment flow must work without WebGL.

### API-facing UI contracts

The UI should expect structured responses, not unbounded prose:

```ts
type ComparisonFact = {
  category: string;
  plain_language: string;
  exact_term?: string;
  source?: { document: string; version?: string; section?: string; page?: number };
  verification_status: 'verified' | 'unverified' | 'conflicting' | 'not_found';
  importance: 'high' | 'medium' | 'low';
};

type RecommendationReport = {
  report_id: string;
  assumptions: string[];
  recommendations: string[];
  tradeoffs: string[];
  facts: ComparisonFact[];
  guardrail_status: 'approved' | 'escalation_required' | 'delivery_hold';
  next_actions: Array<'save' | 'edit' | 'ask_expert' | 'compare_more'>;
};
```

---

## 15. Acceptance checklist

### Landing

- [ ] Visitor understands the product in five seconds without reading a long paragraph.
- [ ] Hero visual represents protection *and* policy gaps, not generic fintech/AI.
- [ ] Primary CTA promises a process, not a purchase.
- [ ] No fabricated testimonials, insurer partnerships, or claim statistics.

### Intake and comparison

- [ ] Each sensitive question says why it is needed.
- [ ] Missing information loop asks the minimum necessary next question.
- [ ] Every comparison field exposes verification status.
- [ ] Trade-offs are as visually prominent as benefits.
- [ ] The user can edit assumptions before results are generated.

### Report and trust

- [ ] Recommendation is conditional on stated priorities.
- [ ] Policy sources and document versions are visible.
- [ ] Guardrail holds prevent a misleading final recommendation.
- [ ] Expert escalation preserves context.
- [ ] Consent and data controls are reachable from every authenticated area.

### Quality

- [ ] Light and dark mode are designed, not auto-inverted.
- [ ] Reduced-motion behavior is tested.
- [ ] Mobile comparison is usable without horizontal table scrolling as the only option.
- [ ] All key flows have loading, empty, error, and partial-data states.

---

## 16. Design north star

A user should finish a session able to say:

> “I understand what I’m choosing, what could still surprise me, and what I should ask next.”

That—not a conversion metric—is the central design outcome.


Assurely — PRD & Product Brief Summary
1. Executive Summary & Vision
Problem Statement: Retail health and term-life insurance in India is broken by high-pressure tele-sales, hidden sub-limits (room rent caps, proportional deduction penalties), and opaque 70-page policy wordings discovered only during hospital billing disputes.
Product Vision: An independent, fiduciary multi-agent advisory platform turning IRDAI public filings into an auditable, interactive "Independent Case File" with zero spam, zero cold calls, and zero commission bias.
2. Core Personas
The Cautious Provider (Rahul, 34, Bengaluru): Needs clarity on parents' pre-existing waiting periods, room-rent sub-limits, and zero tele-marketing spam.
The Self-Directed Researcher (Priya, 29, Mumbai): Needs verifiable IRDAI clause citations, mathematical translations of proportional deductions, and unmanipulated trade-offs.
3. Product Principles & Anti-Patterns
Fiduciary Fit Language: Strictly uses neutral terms ("Finding", "Matches stated priorities", "Coverage gap"). Prohibits sales language like "Best plan", "Top-rated", or "Recommended".
No Contact-Info Gating: Browse, compare, and inspect all clauses without entering a phone number or triggering an OTP.
Document Physicality: Tactile paper sheets, paper clips, inspection magnifying lenses, and exhibits rather than generic SaaS dashboards.
Deterministic Chain of Custody: Every factual statement includes a cryptographic verification stamp: Source: IRDAI Master Schedule → Cross-checked: Actuarial Filing v3.2 → Verified: 2024-06-20.
4. Information Architecture & Key Modules
Living 3D Atmospheric Hero: Multi-depth volumetric cloud decks, morning sun solar warmth, floating family protective canopy island diorama, and 3 pinned gap annotations (Waiting period: 3–6 months [Clay], Room-rent limit: ₹3,000/day [Clay], Day-care surgery covered [Moss]).
Process Architecture: 3-step numbered journey (1. Tell us your priorities → 2. Compare terms that change the outcome → 3. Decide with clarity — or ask an expert).
The Family Case File: Dual-folder dossier switching between Life Insurance Case and Health Insurance Case, featuring UIN verification stamps and multi-source consensus metrics.
"What did they tell you?" Verbal Promise Checker: Evaluates verbal agent sales claims against sworn IRDAI filings, highlighting non-binding discrepancies with Supreme Court case citations (Jacob Punnen v. United India Insurance).
Policy Facts IRDAI Register & Exhibit B Inspector: Structured matrix linked to a physical paper exhibit sheet with a golden paper clip, detailing verbatim clause wording, plain-language translation, and numeric cost impact.
Provenance & Audit Trail: SHA-256 validation checksums, GIC registry IDs, and actuarial versioning stamps.
5. Design System Tokens
Colors: Sky (#EAF1F6), Paper (#F8F3E9), Deep Navy (#16232E), Harbor Accent (#2C5F73), Semantic Risk Clay (#A44A2F), Semantic Verified Moss (#3F6B4A).
Typography: Headlines in IBM Plex Serif, interface & body in IBM Plex Sans, actuarial metadata in IBM Plex Mono, handwritten notes in Caveat.
6. Implementation Roadmap
Phase 0–1: Docker foundation, FastAPI skeleton, Postgres schema, and health domain intake loop.
Phase 2–3: Trust/safety layer, Langfuse observability, and full interactive case-file web UI.
Phase 4: Life insurance domain agent and conversational channels.
