/**
 * ExhibitTag — physical paper exhibit tag with golden paper-clip accent.
 *
 * PRD §4: "Structured matrix linked to a physical paper exhibit sheet
 * with a golden paper clip, detailing verbatim clause wording,
 * plain-language translation, and numeric cost impact."
 *
 * Visual: tactile paper exhibit badge with golden paper-clip edge,
 * monospace clause references, and Harbor label accents.
 *
 * Cross-checked with backend:
 *   - LLD § 7.4 policy_documents (doc_url, version_hash, insurer, product_name)
 *   - AGENTS.md rule 6: Source and last-verified date required.
 */

export interface ExhibitTagProps {
  /** Exhibit identifier, e.g. "Exhibit A", "Exhibit B" */
  exhibitId: string;
  /** Short description of what this exhibit inspects */
  label: string;
  /** Clause cross-reference, e.g. "Section 4.2 · Room Rent Sub-Limit" */
  clauseReference: string;
  /** Source policy document name */
  sourceDocument: string;
  /** Document version or hash */
  sourceVersion?: string;
  /** Two-tier severity level for the inspected finding */
  severity?: "caveat" | "risk" | "neutral";
  /** Date checked */
  lastVerified?: string;
}

const STUB_PROPS: ExhibitTagProps = {
  exhibitId: "Exhibit B",
  label: "Proportional Deduction Penalty Inspection",
  clauseReference: "Section 4.2 · Page 12",
  sourceDocument: "HDFC ERGO Optima Secure",
  sourceVersion: "v2024.01",
  severity: "risk",
  lastVerified: "2024-01-01",
};

export default function ExhibitTag(props: Partial<ExhibitTagProps>) {
  const {
    exhibitId = STUB_PROPS.exhibitId,
    label = STUB_PROPS.label,
    clauseReference = STUB_PROPS.clauseReference,
    sourceDocument = STUB_PROPS.sourceDocument,
    sourceVersion = STUB_PROPS.sourceVersion,
    severity = STUB_PROPS.severity,
    lastVerified = STUB_PROPS.lastVerified,
  } = props;

  const clipGradient =
    severity === "risk"
      ? "from-amber to-clay"
      : "from-sand to-amber";

  return (
    <div className="inline-flex items-stretch rounded-card overflow-hidden border border-line shadow-card bg-surface max-w-sm">
      {/* Tactile paper clip metallic accent */}
      <div className={`w-2.5 bg-gradient-to-b ${clipGradient} flex-shrink-0`} />

      {/* Tag content */}
      <div className="p-4 space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-mono font-semibold uppercase tracking-wider text-harbor bg-harbor-subtle px-2 py-0.5 rounded border border-harbor/20">
            {exhibitId}
          </span>
          {severity === "risk" && (
            <span className="text-[10px] font-mono text-clay bg-clay-subtle px-1.5 py-0.5 rounded uppercase font-semibold">
              Critical Gap
            </span>
          )}
          {severity === "caveat" && (
            <span className="text-[10px] font-mono text-amber bg-amber-subtle px-1.5 py-0.5 rounded uppercase font-semibold">
              Trade-Off
            </span>
          )}
        </div>

        {/* Label */}
        <p className="text-sm font-body font-semibold text-ink leading-snug">
          {label}
        </p>

        {/* Clause reference */}
        <p className="text-xs font-mono text-ink-muted">
          <span className="text-harbor font-semibold uppercase tracking-wider">Clause:</span>{" "}
          {clauseReference}
        </p>

        {/* Source document + version */}
        <p className="text-xs font-mono text-ink-muted">
          <span className="text-harbor font-semibold uppercase tracking-wider">Source:</span>{" "}
          {sourceDocument}
          {sourceVersion && ` (${sourceVersion})`}
        </p>

        {lastVerified && (
          <p className="text-[10px] font-mono text-ink-muted pt-1 border-t border-line/60">
            Verified: {lastVerified}
          </p>
        )}
      </div>
    </div>
  );
}
