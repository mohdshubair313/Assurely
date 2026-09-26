/**
 * ProgressPath — step indicator for multi-step flows.
 *
 * Used in consent, intake, and assessment flows.
 * Shows "Step X of Y" text with optional step labels.
 */

export interface ProgressPathProps {
  currentStep: number;
  totalSteps: number;
  labels?: string[];
  className?: string;
}

export default function ProgressPath({
  currentStep,
  totalSteps,
  labels,
  className = "",
}: ProgressPathProps) {
  return (
    <div className={["w-full", className].join(" ")}>
      {/* Step text */}
      <p className="text-sm font-mono text-ink-muted mb-3">
        Step {currentStep} of {totalSteps}
      </p>

      {/* Progress bar */}
      <div className="flex gap-1.5">
        {Array.from({ length: totalSteps }, (_, i) => {
          const stepIndex = i + 1;
          const isComplete = stepIndex < currentStep;
          const isCurrent = stepIndex === currentStep;

          return (
            <div
              key={stepIndex}
              className="flex-1 flex flex-col gap-1.5"
            >
              {/* Bar segment */}
              <div
                className={[
                  "h-1 rounded-full transition-theme",
                  isComplete && "bg-teal",
                  isCurrent && "bg-sky",
                  !isComplete && !isCurrent && "bg-line",
                ]
                  .filter(Boolean)
                  .join(" ")}
                role="progressbar"
                aria-valuenow={isComplete ? 100 : isCurrent ? 50 : 0}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={labels?.[i] ?? `Step ${stepIndex}`}
              />

              {/* Optional label */}
              {labels?.[i] && (
                <span
                  className={[
                    "text-xs leading-tight",
                    isCurrent ? "text-ink font-medium" : "text-ink-muted",
                  ].join(" ")}
                >
                  {labels[i]}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
