import SectionContainer from "@/components/ui/SectionContainer";
import Card from "@/components/ui/Card";

/**
 * ProcessSteps — "From confusion to confidence — in 5 clear steps."
 *
 * Approved 5-step landing sequence (design.md & PRD):
 * 1. Tell us what matters
 * 2. Compare the terms that change the outcome
 * 3. Understand coverage gaps & trade-offs
 * 4. Decide with clarity — or ask an expert
 * 5. Stay covered (continuous policy tracking & renewal awareness)
 */

const steps = [
  {
    number: 1,
    title: "Tell us what matters",
    description:
      "A short, low-stress conversation about who needs cover, your city, and healthcare priorities — zero phone-number gating, zero cold calls.",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.75} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z" />
      </svg>
    ),
  },
  {
    number: 2,
    title: "Compare terms that change the outcome",
    description:
      "See waiting periods, room-rent sub-limits, co-pay rules, and day-care procedures side by side — checked against sworn IRDAI public filings.",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.75} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21 3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
      </svg>
    ),
  },
  {
    number: 3,
    title: "Understand coverage gaps & trade-offs",
    description:
      "Inspect fine print with physical case-file exhibits. Decode proportional deductions, waiting periods, and room caps before you need hospital admission.",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.75} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607ZM10.5 7.5v6m3-3h-6" />
      </svg>
    ),
  },
  {
    number: 4,
    title: "Decide with clarity — or ask an expert",
    description:
      "Receive an explainable recommendation with complete cryptographic audit provenance. Escalate high-stakes questions to a licensed human advisor.",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.75} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" />
      </svg>
    ),
  },
  {
    number: 5,
    title: "Stay covered",
    description:
      "Continuous policy tracking: annual IRDAI wording change notifications, timely renewal reminders, and claim-dispute guidance when life asks for it.",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.75} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
      </svg>
    ),
  },
];

export default function ProcessSteps() {
  return (
    <SectionContainer as="section" className="py-16 lg:py-24" id="how-it-works">
      <div className="text-center mb-14">
        <p className="text-label font-mono uppercase text-harbor font-semibold tracking-wider mb-3">
          Process Architecture
        </p>
        <h2 className="text-section font-display text-ink">
          From confusion to confidence — in 5 clear steps.
        </h2>
        <p className="mt-4 text-ink-muted max-w-2xl mx-auto font-body text-base">
          We help you understand what insurance actually covers and where trade-offs exist before asking you to choose — not after.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 lg:gap-8">
        {steps.map((step) => (
          <Card
            key={step.number}
            variant="surface"
            className={`p-6 lg:p-7 transition-card hover:-translate-y-1 ${
              step.number === 5 ? "md:col-span-2 lg:col-span-1 bg-harbor-subtle/30 border-harbor/30" : ""
            }`}
            hoverable
          >
            <div className="flex items-center justify-between mb-4">
              <span className="flex items-center justify-center w-10 h-10 rounded-full bg-harbor-subtle text-harbor font-mono font-semibold text-base border border-harbor/20">
                0{step.number}
              </span>
              <span className="text-harbor">{step.icon}</span>
            </div>
            <h3 className="text-lg font-body font-semibold text-ink mb-2.5">
              {step.title}
            </h3>
            <p className="text-sm text-ink-muted leading-relaxed font-body">
              {step.description}
            </p>
          </Card>
        ))}
      </div>

      <div className="text-center mt-12">
        <a
          href="/intake"
          className="inline-flex items-center gap-2 text-harbor hover:text-harbor-strong font-body font-medium transition-theme group"
        >
          Begin your independent assessment
          <svg
            className="w-4 h-4 transition-transform group-hover:translate-x-1"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
          </svg>
        </a>
      </div>
    </SectionContainer>
  );
}
