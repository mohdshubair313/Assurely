"use client";

import { useState } from "react";
import SectionContainer from "@/components/ui/SectionContainer";
import Card from "@/components/ui/Card";

/**
 * ClauseExplainer — interactive policy excerpt with highlighted phrases.
 *
 * design.md §8.1 section 7:
 * A faux policy excerpt with highlighted phrases.
 * Clicking "Room rent limit" reveals a 60-word plain explanation
 * and a "why it matters" example.
 */

interface ClauseTerm {
  id: string;
  term: string;
  clauseText: string;
  explanation: string;
  whyItMatters: string;
  severity: "risk" | "caveat";
}

const clauseTerms: ClauseTerm[] = [
  {
    id: "room-rent",
    term: "Room rent limit",
    clauseText:
      '"The Company shall be liable to pay expenses for room and boarding up to 1% of the Sum Insured or ₹5,000 per day, whichever is lower."',
    explanation:
      "This means the insurer caps what they pay for your hospital room per day. If you choose a room above ₹5,000/day, proportional deductions apply to your entire bill — doctors, surgery, and nursing fees are cut proportionally.",
    whyItMatters:
      "A ₹5,000/day room limit on a ₹10 lakh policy can leave you with a ₹1–2 lakh out-of-pocket gap during a major hospitalisation.",
    severity: "risk",
  },
  {
    id: "waiting-period",
    term: "Waiting period",
    clauseText:
      '"Pre-existing diseases shall be covered after a continuous period of 36 months from the date of inception of the first policy."',
    explanation:
      "The insurer will not pay for treatment of conditions you had before buying the policy for the first 36 months. After continuous 3 years of coverage, they are covered.",
    whyItMatters:
      "If you have diabetes or hypertension, you cannot claim for related hospitalisation during the waiting period — even while paying regular premiums.",
    severity: "caveat",
  },
  {
    id: "co-pay",
    term: "Co-payment clause",
    clauseText:
      '"The insured shall bear 20% of the admissible claim amount for each and every claim."',
    explanation:
      "You pay 20% of every approved claim out of pocket. If an admissible claim is ₹5 lakh, you pay ₹1 lakh yourself — the insurer pays the remaining ₹4 lakh.",
    whyItMatters:
      "Co-pay reduces your yearly premium but directly increases out-of-pocket costs at claim time. Ideal only when conscious of the trade-off.",
    severity: "caveat",
  },
];

export default function ClauseExplainer() {
  const [activeTerm, setActiveTerm] = useState<string>(clauseTerms[0].id);

  const active = clauseTerms.find((t) => t.id === activeTerm) ?? clauseTerms[0];

  return (
    <SectionContainer as="section" className="py-16 lg:py-24" id="what-we-compare">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-12 items-start">
        {/* Left — intro + tabs */}
        <div>
          <p className="text-label font-mono uppercase text-harbor font-semibold tracking-wider mb-3">
            Clarity, not complexity
          </p>
          <h2 className="text-section font-display text-ink mb-6">
            Understand this clause before you sign.
          </h2>

          {/* Term selector tabs */}
          <div className="flex flex-wrap gap-2 mb-6" role="tablist">
            {clauseTerms.map((term) => (
              <button
                key={term.id}
                role="tab"
                aria-selected={activeTerm === term.id}
                onClick={() => setActiveTerm(term.id)}
                className={[
                  "px-4 py-2 rounded-input text-sm font-medium font-body transition-theme cursor-pointer",
                  activeTerm === term.id
                    ? "bg-harbor text-white shadow-sm"
                    : "bg-surface border border-line text-ink-muted hover:text-ink hover:border-harbor",
                ].join(" ")}
              >
                {term.term}
              </button>
            ))}
          </div>

          {/* Explanation */}
          <div className="space-y-4">
            <div>
              <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-harbor mb-2">
                What it means
              </h3>
              <p className="text-ink leading-relaxed font-body">{active.explanation}</p>
            </div>
            <div>
              <h3
                className={`text-xs font-mono font-semibold uppercase tracking-wider mb-2 ${
                  active.severity === "risk" ? "text-clay" : "text-amber"
                }`}
              >
                Why it matters ({active.severity === "risk" ? "Tier 2 Critical Gap" : "Tier 1 Trade-off"})
              </h3>
              <p className="text-ink-muted leading-relaxed font-body">{active.whyItMatters}</p>
            </div>
          </div>
        </div>

        {/* Right — faux policy excerpt */}
        <Card variant="raised" className="p-6 lg:p-8 shadow-card">
          <div className="flex items-center gap-2 mb-4">
            <svg className="w-4 h-4 text-harbor" fill="none" viewBox="0 0 24 24" strokeWidth={1.75} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
            </svg>
            <span className="text-xs font-mono text-ink-muted uppercase tracking-wider">
              Verbatim Policy Excerpt
            </span>
          </div>

          {/* Clause highlight */}
          <blockquote className="border-l-2 border-harbor pl-4 py-2 mb-4 bg-surface-raised/80 rounded-r">
            <p className="text-sm font-mono text-ink leading-relaxed italic">
              {active.clauseText}
            </p>
          </blockquote>

          {/* Source */}
          <div className="pt-3 border-t border-line">
            <p className="text-xs font-mono text-ink-muted">
              <span className="text-harbor font-semibold uppercase tracking-wider">Source:</span>{" "}
              IRDAI Public Policy Filing · Schedule 4
            </p>
          </div>
        </Card>
      </div>
    </SectionContainer>
  );
}
