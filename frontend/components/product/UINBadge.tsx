/**
 * UINBadge — IRDAI Unique Identification Number verification stamp.
 *
 * PRD §4: "UIN verification stamps" on the Family Case File.
 *
 * Visual: compact verification stamp with shield icon, monospace UIN,
 * verification dot (moss if verified, amber if pending),
 * and last-checked date.
 *
 * Cross-checked with backend:
 *   - LLD § 7.4 policy_documents (doc_url, insurer, product_name, version_hash)
 *   - AGENTS.md rule 5: UIN is deterministic (policy_terms lookup).
 *   - AGENTS.md rule 6: Source and last-verified date required.
 */

export interface UINBadgeProps {
  /** IRDAI Unique Identification Number */
  uin?: string;
  /** Insurance product name */
  productName?: string;
  /** Insurance company name */
  insurerName?: string;
  /** Whether this UIN has been verified against IRDAI registry */
  isVerified?: boolean;
  /** ISO date of last verification check */
  lastChecked?: string;
}

const STUB_PROPS: UINBadgeProps = {
  uin: "IRDAIHLTH2926P100001V01202526",
  productName: "Optima Secure Health Insurance",
  insurerName: "HDFC ERGO General Insurance",
  isVerified: true,
  lastChecked: "2024-01-01",
};

export default function UINBadge(props: UINBadgeProps) {
  const {
    uin = STUB_PROPS.uin!,
    productName = STUB_PROPS.productName!,
    insurerName = STUB_PROPS.insurerName!,
    isVerified = STUB_PROPS.isVerified!,
    lastChecked = STUB_PROPS.lastChecked!,
  } = props;

  return (
    <div
      className={[
        "inline-flex items-start gap-3 p-3 rounded-card border shadow-sm",
        "bg-surface max-w-sm transition-theme",
        isVerified ? "border-moss/40" : "border-amber/40",
      ].join(" ")}
    >
      {/* Shield verification icon */}
      <div
        className={[
          "flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center",
          isVerified ? "bg-moss-subtle text-moss" : "bg-amber-subtle text-amber",
        ].join(" ")}
      >
        <svg
          className="w-5 h-5"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.75}
          stroke="currentColor"
        >
          {isVerified ? (
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z"
            />
          ) : (
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 9v3.75m0 3.75h.008v.008H12v-.008ZM12 2.714a11.959 11.959 0 0 1 8.4 3.286A12 12 0 0 1 21 9.75c0 5.592-3.824 10.29-9 11.622-5.176-1.332-9-6.03-9-11.622 0-1.31.21-2.571.598-3.751h.152c3.196 0 6.1-1.248 8.25-3.285Z"
            />
          )}
        </svg>
      </div>

      {/* Details */}
      <div className="min-w-0 space-y-1">
        <p className="text-xs font-mono text-ink-muted break-all leading-tight">
          <span className="text-harbor font-semibold uppercase tracking-wider">UIN:</span>{" "}
          {uin}
        </p>

        <p className="text-sm font-body text-ink font-semibold leading-tight truncate">
          {productName}
        </p>
        <p className="text-xs text-ink-muted truncate font-body">{insurerName}</p>

        <div className="flex items-center gap-2 pt-0.5">
          <span
            className={[
              "inline-block w-1.5 h-1.5 rounded-full",
              isVerified ? "bg-moss" : "bg-amber",
            ].join(" ")}
          />
          <span className="text-[10px] font-mono text-ink-muted">
            {isVerified ? "IRDAI Verified" : "Verification Pending"} · {lastChecked}
          </span>
        </div>
      </div>
    </div>
  );
}
