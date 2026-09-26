import type { Metadata } from "next";
import SectionContainer from "@/components/ui/SectionContainer";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import AgentClaimChecker from "@/components/product/AgentClaimChecker";

/**
 * Human Advisor Handoff page — from Stitch export.
 *
 * design.md §8.8:
 * Escalation UI: "A licensed advisor will review your comparison."
 * Shows what is being shared, the reason for handoff, and the
 * agent-claim-checker widget.
 *
 * AGENTS.md rule 4: guardrail approves, does not write output.
 * Escalation gates delivery, not generation.
 */

export const metadata: Metadata = {
  title: "Expert Review — Assurely",
  description:
    "A licensed insurance advisor will review your comparison and address any questions the AI could not confidently answer.",
};

export default function HandoffPage() {
  return (
    <SectionContainer className="py-8 lg:py-12">
      <div className="max-w-3xl mx-auto space-y-8">
        {/* Header */}
        <div className="text-center">
          <div className="w-14 h-14 mx-auto mb-4 rounded-full bg-teal-subtle border-2 border-teal flex items-center justify-center">
            <svg className="w-7 h-7 text-teal" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
            </svg>
          </div>
          <h1 className="text-section font-display text-ink mb-2">
            A licensed advisor will review your comparison
          </h1>
          <p className="text-ink-muted max-w-lg mx-auto">
            Some questions need human expertise. We&apos;re connecting you with a
            licensed insurance advisor who will review your case.
          </p>
        </div>

        {/* Why handoff */}
        <Card variant="raised" className="p-6 lg:p-8 space-y-5">
          <h2 className="text-h3 font-body text-ink">
            Why we&apos;re asking for expert review
          </h2>

          <div className="space-y-3">
            {[
              {
                icon: "⚠️",
                reason: "Your situation includes a pre-existing condition that may affect portability terms across insurers.",
              },
              {
                icon: "📋",
                reason: "The verbal promises from your agent do not match the policy document — an advisor can help you navigate this.",
              },
              {
                icon: "🔍",
                reason: "One comparison fact could not be verified against available policy documents.",
              },
            ].map((item, i) => (
              <div key={i} className="flex items-start gap-3 p-3 rounded-card bg-surface border border-line">
                <span className="text-lg flex-shrink-0">{item.icon}</span>
                <p className="text-sm text-ink leading-relaxed">{item.reason}</p>
              </div>
            ))}
          </div>
        </Card>

        {/* What will be shared */}
        <Card variant="surface" className="p-6 lg:p-8 space-y-5">
          <h2 className="text-h3 font-body text-ink">
            What the advisor will see
          </h2>
          <p className="text-sm text-ink-muted">
            We only share what&apos;s needed for the review. You control what stays
            private.
          </p>

          <div className="space-y-2">
            {[
              { label: "Your comparison report", shared: true },
              { label: "Family composition and budget range", shared: true },
              { label: "Verification status of each fact", shared: true },
              { label: "Your personal details (name, email)", shared: false },
              { label: "Your full conversation history", shared: false },
            ].map((item) => (
              <div key={item.label} className="flex items-center gap-3 py-2">
                {item.shared ? (
                  <svg className="w-4 h-4 text-teal flex-shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4 text-ink-muted flex-shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                  </svg>
                )}
                <span className={`text-sm ${item.shared ? "text-ink" : "text-ink-muted"}`}>
                  {item.label}
                </span>
              </div>
            ))}
          </div>
        </Card>

        {/* Agent claim checker */}
        <div>
          <h2 className="text-h3 font-body text-ink mb-4">
            What did the agent tell you?
          </h2>
          <p className="text-sm text-ink-muted mb-4">
            If a sales agent made verbal claims, we check them against the filed
            policy documents.
          </p>
          <AgentClaimChecker />
        </div>

        {/* Actions */}
        <div className="flex flex-col sm:flex-row items-center gap-4 pt-4 border-t border-line">
          <Button size="lg" className="w-full sm:w-auto">
            Connect with an advisor
          </Button>
          <Button variant="secondary" size="lg" className="w-full sm:w-auto">
            Download comparison first
          </Button>
        </div>

        {/* Privacy note */}
        <p className="text-xs text-ink-muted text-center">
          All conversations with advisors are logged. You can revoke data sharing
          at any time from your account settings.
        </p>
      </div>
    </SectionContainer>
  );
}
