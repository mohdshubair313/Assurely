/**
 * EvidenceLabel — monospace source metadata block.
 *
 * Renders policy source references in IBM Plex Mono per design.md §8.7:
 *   SOURCE  Policy wording v2026.04
 *   CLAUSE  Section 5.2 · page 17
 *   STATUS  Verified against stored policy terms
 *
 * Every claim in output carries a source and last-verified date (AGENTS.md rule 6).
 */

export interface EvidenceLabelProps {
  entries: Array<{
    key: string;
    value: string;
  }>;
  lastVerified?: string;
  className?: string;
}

export default function EvidenceLabel({
  entries,
  lastVerified,
  className = "",
}: EvidenceLabelProps) {
  return (
    <div
      className={[
        "font-mono text-xs leading-relaxed",
        "p-3 rounded-input",
        "bg-surface border border-line",
        "text-ink-muted",
        className,
      ].join(" ")}
    >
      <dl className="space-y-1">
        {entries.map((entry) => (
          <div key={entry.key} className="flex gap-3">
            <dt className="text-label uppercase font-semibold tracking-wider text-harbor min-w-[5rem]">
              {entry.key}
            </dt>
            <dd className="text-ink">{entry.value}</dd>
          </div>
        ))}
      </dl>
      {lastVerified && (
        <p className="mt-2 pt-2 border-t border-line text-ink-muted text-label">
          Last verified: {lastVerified}
        </p>
      )}
    </div>
  );
}
