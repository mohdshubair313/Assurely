/**
 * StatusPill — verification status indicator.
 *
 * Used in comparison tables and evidence views. Always includes text —
 * never relies on hue alone (design.md §11).
 *
 * Implements two-tier severity:
 *   - "verified": Moss (#3F6B4A) confirmed policy term
 *   - "needs-review" / "caveat": Amber (#B96A18) Tier 1 attention notice
 *   - "conflicting" / "risk": Clay (#A44A2F) Tier 2 critical discrepancy or exclusion
 *   - "not-found": Neutral status
 */

export type VerificationStatus =
  | "verified"
  | "needs-review"
  | "not-found"
  | "conflicting"
  | "caveat"
  | "risk";

export interface StatusPillProps {
  status: VerificationStatus;
  className?: string;
}

const statusConfig: Record<
  VerificationStatus,
  { label: string; dotClass: string; bgClass: string; textClass: string }
> = {
  verified: {
    label: "Verified",
    dotClass: "bg-moss",
    bgClass: "bg-moss-subtle",
    textClass: "text-moss",
  },
  "needs-review": {
    label: "Needs review",
    dotClass: "bg-amber",
    bgClass: "bg-amber-subtle",
    textClass: "text-amber",
  },
  caveat: {
    label: "Trade-off note",
    dotClass: "bg-amber",
    bgClass: "bg-amber-subtle",
    textClass: "text-amber",
  },
  "not-found": {
    label: "Not found",
    dotClass: "bg-ink-muted",
    bgClass: "bg-surface",
    textClass: "text-ink-muted",
  },
  conflicting: {
    label: "Discrepancy",
    dotClass: "bg-clay",
    bgClass: "bg-clay-subtle",
    textClass: "text-clay",
  },
  risk: {
    label: "Coverage Gap",
    dotClass: "bg-clay",
    bgClass: "bg-clay-subtle",
    textClass: "text-clay",
  },
};

export default function StatusPill({
  status,
  className = "",
}: StatusPillProps) {
  const config = statusConfig[status] || statusConfig["not-found"];

  return (
    <span
      className={[
        "inline-flex items-center gap-1.5",
        "px-2.5 py-1",
        "text-xs font-medium font-mono uppercase tracking-wider",
        "rounded-full border border-line",
        config.bgClass,
        config.textClass,
        className,
      ].join(" ")}
    >
      <span
        className={`inline-block w-1.5 h-1.5 rounded-full ${config.dotClass}`}
        aria-hidden="true"
      />
      {config.label}
    </span>
  );
}
