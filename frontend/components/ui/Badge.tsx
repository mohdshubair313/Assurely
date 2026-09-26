import type { ReactNode } from "react";

/**
 * Badge — small label with semantic color variants.
 *
 * Implements the two-tier severity split:
 *   - "caution" (Tier 1 Amber): Attention, trade-offs, co-pays, financial conditions
 *   - "risk" (Tier 2 Clay): Critical gaps, exclusions, room-rent proportional deduction penalties
 *   - "verified": Moss / Teal confirmation
 *   - "harbor": Primary case-file label
 *   - "info": Sky Blue secondary accent
 *   - "neutral": Muted metadata
 */

type BadgeVariant =
  | "primary"
  | "info"
  | "verified"
  | "caution"
  | "risk"
  | "neutral";

export interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
}

const variantClasses: Record<BadgeVariant, string> = {
  primary: "bg-harbor-subtle text-harbor border-harbor/30",
  info: "bg-sky-subtle text-sky-strong border-sky/30",
  verified: "bg-moss-subtle text-moss border-moss/30",
  caution: "bg-amber-subtle text-amber border-amber/30",
  risk: "bg-clay-subtle text-clay border-clay/30",
  neutral: "bg-surface text-ink-muted border-line",
};

export default function Badge({
  children,
  variant = "neutral",
  className = "",
}: BadgeProps) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1",
        "px-2.5 py-0.5",
        "text-xs font-medium font-body leading-tight",
        "border rounded-full",
        "transition-theme",
        variantClasses[variant],
        className,
      ].join(" ")}
    >
      {children}
    </span>
  );
}
