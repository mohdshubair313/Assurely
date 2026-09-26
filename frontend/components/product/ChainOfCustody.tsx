/**
 * ChainOfCustody — deterministic provenance trail.
 *
 * PRD §4: "SHA-256 validation checksums, GIC registry IDs,
 * and actuarial versioning stamps."
 *
 * Cross-checked against backend:
 *   - LLD § 7.4 / audit_log table (session_id, node_name, input_hash, output_hash, sources_json)
 *   - LLD § 7.4 / decision_trace table
 *   - backend/app/api/v1/message.py MessageResponse.session_id
 *   - AGENTS.md rule 6: Every claim carries source + last-verified date.
 */

export interface CustodyStep {
  /** Action description, e.g. "Source: IRDAI Master Schedule" */
  action: string;
  /** Responsible node / entity, e.g. "needs_intake", "rules_engine", "guardrail" */
  entity: string;
  /** ISO timestamp from audit_log.created_at */
  timestamp: string;
  /** SHA-256 checksum from audit_log.input_hash / output_hash / version_hash */
  hash?: string;
  /** Version reference, e.g. "Actuarial Filing v3.2" */
  version?: string;
}

export interface ChainOfCustodyProps {
  /** Session ID or Report ID */
  reportId?: string;
  /** Ordered list of provenance steps */
  steps?: CustodyStep[];
}

/** Stub steps mirroring backend's actual LangGraph execution flow */
const STUB_STEPS: CustodyStep[] = [
  {
    action: "Intake & Profile Extraction",
    entity: "LangGraph node: needs_intake",
    timestamp: "2026-09-21T10:30:00Z",
    hash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    version: "HealthCoverSizing v1.0",
  },
  {
    action: "Deterministic Policy Terms Lookup",
    entity: "Postgres table: policy_terms",
    timestamp: "2026-09-21T10:30:02Z",
    hash: "7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
    version: "HDFC-ERGO-v2024.01",
  },
  {
    action: "Compliance Check & Anti-Ranking Audit",
    entity: "LangGraph node: guardrail",
    timestamp: "2026-09-21T10:30:05Z",
    hash: "c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
    version: "AGENTS-Rule1-Verified",
  },
];

function truncateHash(hash: string): string {
  if (hash.length <= 16) return hash;
  return `${hash.slice(0, 8)}…${hash.slice(-4)}`;
}

export default function ChainOfCustody({
  reportId = "SESSION-8a4f91e2",
  steps = STUB_STEPS,
}: ChainOfCustodyProps) {
  return (
    <div className="bg-surface rounded-card border border-line p-6 max-w-md shadow-card">
      {/* Header */}
      <div className="flex items-center justify-between mb-5 pb-3 border-b border-line">
        <h3 className="text-sm font-mono font-semibold uppercase tracking-wider text-harbor">
          Deterministic Chain of Custody
        </h3>
        <span className="text-xs font-mono text-ink-muted bg-surface-raised px-2 py-0.5 rounded border border-line">
          {reportId}
        </span>
      </div>

      {/* Timeline */}
      <div className="relative">
        {/* Vertical verification line */}
        <div
          className="absolute left-3 top-2 bottom-2 w-0.5 bg-moss/60"
          aria-hidden="true"
        />

        <ol className="space-y-5">
          {steps.map((step, index) => (
            <li key={index} className="relative pl-8">
              {/* Dot */}
              <div
                className={[
                  "absolute left-1.5 top-1.5 w-3 h-3 rounded-full border-2 transition-theme",
                  index === steps.length - 1
                    ? "bg-moss border-moss ring-4 ring-moss-subtle"
                    : "bg-surface border-moss",
                ].join(" ")}
                aria-hidden="true"
              />

              {/* Content */}
              <div className="space-y-1">
                <p className="text-sm font-body font-semibold text-ink">
                  {step.action}
                </p>
                <p className="text-xs font-mono text-ink-muted">{step.entity}</p>

                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="text-xs font-mono text-ink-muted">
                    {new Date(step.timestamp).toLocaleTimeString("en-IN", {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </span>
                  {step.version && (
                    <span className="text-xs font-mono text-moss bg-moss-subtle px-1.5 py-0.2 rounded">
                      {step.version}
                    </span>
                  )}
                </div>

                {/* Monospace SHA-256 hash stamp */}
                {step.hash && (
                  <p
                    className="text-[10px] font-mono text-ink-muted bg-surface-raised px-2 py-0.5 rounded inline-block mt-1 border border-line"
                    title={`SHA-256: ${step.hash}`}
                  >
                    SHA-256: {truncateHash(step.hash)}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
