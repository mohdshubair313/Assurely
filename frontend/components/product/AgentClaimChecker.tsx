import Card from "@/components/ui/Card";
import StatusPill from "@/components/ui/StatusPill";

/**
 * AgentClaimChecker — "What did they tell you?" verbal promise checker.
 *
 * PRD §4: "Evaluates verbal agent sales claims against sworn IRDAI
 * filings, highlighting non-binding discrepancies with Supreme Court
 * case citations (Jacob Punnen v. United India Insurance)."
 *
 * Cross-checked against backend:
 *   - Matches user verbal claims against policy_terms & retrieved_facts.
 *   - Flags discrepancies using the two-tier severity system (Clay for binding mismatches).
 *   - AGENTS.md rule 6: Every claim carries source + last-verified date.
 */

export interface AgentClaimCheckerProps {
  /** What the sales agent verbally claimed */
  verbalClaim?: string;
  /** IRDAI verification finding */
  irdaiFinding?: {
    matches: boolean;
    clause_wording: string;
    source: string;
    discrepancies: string[];
    case_citations?: string[];
  };
  /** ISO date of last verification check */
  lastVerified?: string;
}

const STUB_PROPS: AgentClaimCheckerProps = {
  verbalClaim:
    "Don't worry sir, all hospital rooms are 100% covered with no limit at all in this plan.",
  irdaiFinding: {
    matches: false,
    clause_wording:
      "Room and boarding expenses up to 1% of Sum Insured or ₹5,000/day, whichever is lower.",
    source: "HDFC ERGO Optima Secure Policy Wordings 2024 · Section 4.2 · Page 12",
    discrepancies: [
      "Agent promised unlimited room rent — sworn policy filing caps rooms at ₹5,000/day",
      "Proportional deduction penalty on higher rooms was omitted by the agent",
    ],
    case_citations: [
      "Jacob Punnen & Anr. v. United India Insurance Co. Ltd. (2022 SC) — Insurer bound strictly by filed policy terms, not verbal promises.",
    ],
  },
  lastVerified: "2024-01-01",
};

export default function AgentClaimChecker(props: AgentClaimCheckerProps) {
  const {
    verbalClaim = STUB_PROPS.verbalClaim!,
    irdaiFinding = STUB_PROPS.irdaiFinding!,
    lastVerified = STUB_PROPS.lastVerified!,
  } = props;

  const statusVariant = irdaiFinding.matches ? "verified" : "conflicting";

  return (
    <Card variant="raised" className="overflow-hidden max-w-lg shadow-card">
      {/* Header */}
      <div className="bg-harbor-subtle px-6 py-3 border-b border-line flex items-center justify-between">
        <h3 className="text-sm font-mono font-semibold uppercase tracking-wider text-harbor">
          What did they tell you?
        </h3>
        <span className="text-xs font-mono text-ink-muted">
          Verbal Promise Checker
        </span>
      </div>

      <div className="p-6 space-y-5">
        {/* Verbal claim quote box */}
        <div className="bg-sand-subtle border border-sand/60 rounded-card p-4">
          <p className="text-xs font-mono text-ink-muted uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-sand" />
            Agent&apos;s Verbal Representation
          </p>
          <blockquote className="text-sm text-ink italic leading-relaxed font-body">
            &ldquo;{verbalClaim}&rdquo;
          </blockquote>
        </div>

        {/* IRDAI finding */}
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <StatusPill status={statusVariant} />
            <span className="text-xs font-body text-ink-muted">
              {irdaiFinding.matches
                ? "Verbal claim matches sworn IRDAI filing"
                : "Discrepancy found against policy filing"}
            </span>
          </div>

          {/* Actual policy clause */}
          <div>
            <p className="text-xs font-mono text-harbor font-semibold uppercase tracking-wider mb-1.5">
              Sworn IRDAI Policy Wording
            </p>
            <blockquote className="border-l-2 border-harbor/50 pl-3 text-sm font-mono text-ink-muted italic bg-surface-raised py-1 rounded-r">
              &ldquo;{irdaiFinding.clause_wording}&rdquo;
            </blockquote>
          </div>

          {/* Discrepancies flagged in Clay */}
          {irdaiFinding.discrepancies.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-mono text-clay font-semibold uppercase tracking-wider">
                Discrepancies Identified
              </p>
              <ul className="space-y-1.5">
                {irdaiFinding.discrepancies.map((d, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-sm text-ink bg-clay-subtle/50 p-2.5 rounded border border-clay/20"
                  >
                    <svg
                      className="w-4 h-4 text-clay mt-0.5 flex-shrink-0"
                      fill="none"
                      viewBox="0 0 24 24"
                      strokeWidth={2}
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
                      />
                    </svg>
                    <span className="text-xs font-body leading-relaxed">{d}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Case citations */}
          {irdaiFinding.case_citations && irdaiFinding.case_citations.length > 0 && (
            <div className="pt-3 border-t border-line">
              <p className="text-xs font-mono text-ink-muted uppercase tracking-wider mb-1.5">
                Supreme Court Precedent
              </p>
              {irdaiFinding.case_citations.map((c, i) => (
                <p key={i} className="text-xs font-mono text-harbor bg-harbor-subtle/60 p-2 rounded">
                  ⚖️ {c}
                </p>
              ))}
            </div>
          )}
        </div>

        {/* Source footer */}
        <div className="pt-3 border-t border-line flex items-center justify-between flex-wrap gap-2 text-xs font-mono text-ink-muted">
          <p>
            <span className="text-harbor font-semibold uppercase tracking-wider">Source:</span>{" "}
            {irdaiFinding.source}
          </p>
          <p>Verified: {lastVerified}</p>
        </div>
      </div>
    </Card>
  );
}
