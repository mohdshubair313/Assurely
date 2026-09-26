import SectionContainer from "@/components/ui/SectionContainer";
import Card from "@/components/ui/Card";
import EvidenceLabel from "@/components/ui/EvidenceLabel";

/**
 * TrustSection — "Every recommendation has a trail."
 *
 * design.md §8.1 section 9:
 * Show source, plan version, facts used, missing information,
 * and review status. Trust ledger pattern.
 */

export default function TrustSection() {
  return (
    <SectionContainer as="section" className="py-16 lg:py-24" id="trust">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-12 items-center">
        {/* Left — copy */}
        <div>
          <p className="text-label font-mono uppercase text-ink-muted mb-3">
            Transparency built in
          </p>
          <h2 className="text-section font-display text-ink mb-6">
            Every recommendation has a trail.
          </h2>
          <p className="text-ink-muted leading-relaxed mb-6 max-w-lg">
            Assurely is designed to show its reasoning: which policy terms were
            checked, what information was used, what assumptions were made, and
            where a human expert should review.
          </p>

          <ul className="space-y-3">
            {[
              "Policy source and document version",
              "Facts used in comparison",
              "Assumptions and missing information",
              "Verification status of each claim",
              "When to consult a licensed advisor",
            ].map((item) => (
              <li key={item} className="flex items-start gap-2.5 text-sm text-ink">
                <svg className="w-4 h-4 text-teal mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                </svg>
                {item}
              </li>
            ))}
          </ul>
        </div>

        {/* Right — evidence example */}
        <Card variant="raised" className="p-6 lg:p-8 space-y-4">
          <h3 className="text-sm font-mono font-semibold uppercase tracking-wider text-harbor">
            Sample decision trail
          </h3>

          <EvidenceLabel
            entries={[
              { key: "Source", value: "Policy wording v2026.04" },
              { key: "Clause", value: "Section 5.2 · page 17" },
              { key: "Status", value: "Verified against stored policy terms" },
            ]}
            lastVerified="2026-06-20"
          />

          <div className="pt-3 border-t border-line">
            <h4 className="text-xs font-mono text-ink-muted uppercase tracking-wider mb-2">
              Inputs used
            </h4>
            <div className="flex flex-wrap gap-2">
              {["2 adults + 1 child", "Moderate budget", "Cashless network priority"].map(
                (tag) => (
                  <span
                    key={tag}
                    className="text-xs px-2.5 py-1 bg-sand-subtle text-ink rounded-full border border-sand"
                  >
                    {tag}
                  </span>
                )
              )}
            </div>
          </div>

          <div className="pt-3 border-t border-line">
            <h4 className="text-xs font-mono text-ink-muted uppercase tracking-wider mb-2">
              Not available
            </h4>
            <p className="text-sm text-amber">
              Current policy details not provided — comparison may miss renewal terms
            </p>
          </div>
        </Card>
      </div>
    </SectionContainer>
  );
}
