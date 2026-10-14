---
name: hero-ui
description: Design, implement, or refine an app or landing-page hero section with coherent visual hierarchy, responsive layout, accessible interactions, and browser-based visual checks. Use for hero-section UI work, not unrelated page redesigns or backend changes.
---

# Hero UI

Create a polished hero that makes the product purpose and primary action clear. Interpret requests for a perfect UI as a request for careful implementation and observable verification; do not promise universal visual perfection.

## Understand the existing screen

Read applicable AGENTS.md and project progress instructions. Inspect the hero, navigation, surrounding section, design tokens, component library, framework version, and existing assets before changing code. Read project design guidance when present, including docs/design.md in InsuranceAI. Treat implemented tokens and current phase constraints as authoritative when older design concepts describe future functionality.

Identify the audience, value proposition, primary action, and whether the user wants implementation, a mockup, or a critique. Honor supplied references and brand choices. Ask only when a missing decision materially changes the result; otherwise state reasonable assumptions and proceed within scope. A hero request does not authorize a full-site redesign or deployment.

## Compose the layout

- Establish a deliberate hierarchy: concise headline, useful supporting copy, primary action, and a relevant visual. Add secondary actions or trust information only when they support the user journey.
- Select a centered, split, or editorial composition based on content and available space. Keep the text and illustration balanced without forcing a fixed template.
- Align the hero with the navigation and neighboring content using shared containers, spacing tokens, and a coherent typography scale. Use a bounded reading width and fluid type sizes; check actual line breaks rather than forcing them for one screen size.
- Use intentional contrast and whitespace. Keep decoration behind readable content and preserve a clear focus on the action. Do not introduce arbitrary gradients, extra fonts, excessive cards, or shadows that conflict with the brand.
- Preserve working links and interaction contracts. Wire actions to existing destinations; if none exists, report that gap rather than implying a working flow.

## Responsive behavior

Use content-driven breakpoints, fluid containers, CSS grid or flex layouts, and intrinsic image sizing. Allow the hero to grow with its content instead of clipping it into a fixed viewport height.

On narrow screens, keep the headline, explanation, and primary action in a sensible reading order. Stack columns when needed; adapt visual cropping and button layout rather than merely shrinking the desktop screen. Ensure long text, enlarged fonts, device safe areas, and sticky navigation cannot cause overlaps or horizontal overflow. Avoid hiding essential information to make a screenshot fit.

Inspect representative widths such as 360, 390, 768, 1024, and 1440 CSS pixels, plus a narrow 320-pixel screen and a short landscape viewport when relevant. These are practical coverage examples, not substitutes for checking intermediate widths where the layout changes.

## Accessibility, motion, and performance

Use semantic headings appropriate to the page, native links and buttons, visible focus states, meaningful accessible names, useful image alternatives, and decorative-image exclusion from the accessibility tree. Maintain readable contrast and comfortable touch targets. Do not put essential copy inside images or require hover to reveal essential information.

Support keyboard navigation and text enlargement. Respect reduced-motion preferences; provide a static equivalent for animated illustrations. Keep motion subtle enough for reading and avoid continuous effects that obscure content.

Reuse the app's image and font loading facilities. Reserve image dimensions to reduce layout shifts, choose appropriate responsive assets, and keep optional video or 3D effects from delaying the primary content. Add dependencies only when an actual requirement justifies them.

## InsuranceAI context

When working in InsuranceAI, preserve Assurely's calm, explanatory tone and the existing Harbor, Sky Blue, cream, ink, and IBM Plex design language as defined by current tokens. Frame policy comparisons by individual needs. Follow repository restrictions on comparative wording and factual provenance. Do not invent premiums, policy benefits, insurer endorsements, reviews, customer counts, or certification badges. Keep the hero within the current health-insurance web scope and avoid presenting roadmap features as available. Schema and graph-routing changes require flagging under repository instructions and are outside ordinary hero work.

## Verify the delivered screen

Run relevant frontend build, lint, or type checks available in the project. With an available browser tool, render the actual app and inspect screenshots at representative mobile, tablet, and desktop sizes. Check text wrapping, spacing, overflow, image crop, navigation clearance, focus visibility, action behavior, and reduced motion. Fix observed defects and recheck affected screens.

If browser access or an app dependency prevents visual verification, explicitly report which checks remain unverified; do not label a code-only review as visual verification. Add automated tests only for meaningful behavior or demonstrated regressions, not to mirror styling values.

Summarize what changed, files affected, screen sizes inspected, checks completed, and remaining limitations. Update project progress when required.
