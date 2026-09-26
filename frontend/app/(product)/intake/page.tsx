"use client";

import { useState } from "react";
import SectionContainer from "@/components/ui/SectionContainer";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import ProgressPath from "@/components/ui/ProgressPath";

/**
 * Guided Intake page — from Stitch export.
 *
 * design.md §8.3:
 * Conversation-style intake (NOT a 40-field form).
 * Collects: family, priorities, budget, existing cover.
 * Cross-checked with backend needs_intake state:
 *   - missing_fields: age, city_tier, dependents, pre_existing_conditions
 */

const intakeSteps = [
  { label: "Family", key: "family" },
  { label: "Priorities", key: "priorities" },
  { label: "Budget", key: "budget" },
  { label: "Existing cover", key: "existing" },
] as const;

export default function IntakePage() {
  const [currentStep, setCurrentStep] = useState(1);

  return (
    <SectionContainer className="py-8 lg:py-12">
      <div className="max-w-2xl mx-auto space-y-8">
        {/* Progress Path */}
        <ProgressPath
          currentStep={currentStep}
          totalSteps={intakeSteps.length}
          labels={intakeSteps.map((s) => s.label)}
        />

        {/* Step content */}
        <Card variant="raised" className="p-6 lg:p-8 shadow-card">
          {currentStep === 1 && (
            <div className="space-y-6">
              <div>
                <h1 className="text-h3 font-body text-ink mb-2">
                  Let&apos;s start with who needs cover
                </h1>
                <p className="text-sm font-body text-ink-muted">
                  This helps us calculate the baseline sum insured without guesswork.
                </p>
              </div>

              <div className="space-y-4">
                <div>
                  <label htmlFor="adults" className="block text-sm font-medium font-body text-ink mb-1.5">
                    Number of adults
                  </label>
                  <select
                    id="adults"
                    defaultValue="2"
                    className="w-full px-4 py-2.5 rounded-input border border-line bg-surface text-ink font-body transition-theme focus:ring-2 focus:ring-harbor focus:border-harbor"
                  >
                    <option value="1">1 adult</option>
                    <option value="2">2 adults</option>
                    <option value="3">3 adults</option>
                  </select>
                </div>

                <div>
                  <label htmlFor="children" className="block text-sm font-medium font-body text-ink mb-1.5">
                    Number of children
                  </label>
                  <select
                    id="children"
                    defaultValue="1"
                    className="w-full px-4 py-2.5 rounded-input border border-line bg-surface text-ink font-body transition-theme focus:ring-2 focus:ring-harbor focus:border-harbor"
                  >
                    <option value="0">No children</option>
                    <option value="1">1 child</option>
                    <option value="2">2 children</option>
                    <option value="3">3 children</option>
                  </select>
                </div>

                <div>
                  <label htmlFor="eldest-age" className="block text-sm font-medium font-body text-ink mb-1.5">
                    Age of eldest member
                  </label>
                  <input
                    id="eldest-age"
                    type="number"
                    min="18"
                    max="99"
                    placeholder="34"
                    className="w-full px-4 py-2.5 rounded-input border border-line bg-surface text-ink font-body placeholder:text-ink-muted transition-theme focus:ring-2 focus:ring-harbor focus:border-harbor"
                  />
                </div>

                <div>
                  <label htmlFor="city-tier" className="block text-sm font-medium font-body text-ink mb-1.5">
                    Primary city / treatment tier
                  </label>
                  <select
                    id="city-tier"
                    defaultValue="tier_1"
                    className="w-full px-4 py-2.5 rounded-input border border-line bg-surface text-ink font-body transition-theme focus:ring-2 focus:ring-harbor focus:border-harbor"
                  >
                    <option value="tier_1">Tier 1 (Metro: Bengaluru, Delhi NCR, Mumbai, Chennai)</option>
                    <option value="tier_2">Tier 2 (State Capitals & Major Hubs)</option>
                    <option value="tier_3">Tier 3 / Other</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {currentStep === 2 && (
            <div className="space-y-6">
              <div>
                <h1 className="text-h3 font-body text-ink mb-2">
                  What matters most to you?
                </h1>
                <p className="text-sm font-body text-ink-muted">
                  Select priorities — this configures deterministic need-fit filtering.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {[
                  "No room-rent sub-limit (single private room)",
                  "Short waiting period for pre-existing disease",
                  "Zero co-payment penalty",
                  "Broad cashless hospital network in my city",
                  "Day-care procedure coverage (cataract, chemo)",
                  "Restoration / recharge benefit",
                  "Maternity & newborn cover rider",
                  "Consumables & non-medical items cover",
                ].map((priority) => (
                  <label
                    key={priority}
                    className="flex items-center gap-3 p-3 rounded-card border border-line bg-surface hover:border-harbor cursor-pointer transition-theme"
                  >
                    <input type="checkbox" className="accent-harbor w-4 h-4" />
                    <span className="text-sm font-body text-ink">{priority}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {currentStep === 3 && (
            <div className="space-y-6">
              <div>
                <h1 className="text-h3 font-body text-ink mb-2">
                  What&apos;s your annual premium budget?
                </h1>
                <p className="text-sm font-body text-ink-muted">
                  Annual premium budget per household — we verify premiums against rate tables.
                </p>
              </div>

              <div className="space-y-3">
                {[
                  "Under ₹15,000 / year",
                  "₹15,000 – ₹25,000 / year",
                  "₹25,000 – ₹40,000 / year",
                  "₹40,000 – ₹60,000 / year",
                  "Above ₹60,000 / year",
                  "Show optimal need-fit regardless of budget",
                ].map((range) => (
                  <label
                    key={range}
                    className="flex items-center gap-3 p-3 rounded-card border border-line bg-surface hover:border-harbor cursor-pointer transition-theme"
                  >
                    <input type="radio" name="budget" className="accent-harbor w-4 h-4" />
                    <span className="text-sm font-body text-ink">{range}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {currentStep === 4 && (
            <div className="space-y-6">
              <div>
                <h1 className="text-h3 font-body text-ink mb-2">
                  Do you have existing health cover?
                </h1>
                <p className="text-sm font-body text-ink-muted">
                  Helps identify waiting-period credit portability under IRDAI guidelines.
                </p>
              </div>

              <div className="space-y-3">
                {[
                  { value: "yes", label: "Yes — I hold an active retail health policy" },
                  { value: "employer", label: "Only through employer group insurance (GMC)" },
                  { value: "no", label: "No — this will be my household's first policy" },
                  { value: "unsure", label: "I am not sure of the current status" },
                ].map((option) => (
                  <label
                    key={option.value}
                    className="flex items-center gap-3 p-3 rounded-card border border-line bg-surface hover:border-harbor cursor-pointer transition-theme"
                  >
                    <input type="radio" name="existing-cover" className="accent-harbor w-4 h-4" />
                    <span className="text-sm font-body text-ink">{option.label}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* Navigation */}
          <div className="flex items-center justify-between mt-8 pt-6 border-t border-line">
            <Button
              variant="ghost"
              size="sm"
              disabled={currentStep === 1}
              onClick={() => setCurrentStep((s) => Math.max(1, s - 1))}
            >
              ← Back
            </Button>

            {currentStep < intakeSteps.length ? (
              <Button
                variant="primary"
                size="sm"
                onClick={() => setCurrentStep((s) => Math.min(intakeSteps.length, s + 1))}
              >
                Continue →
              </Button>
            ) : (
              <a href="/comparison">
                <Button variant="primary" size="sm">
                  Generate Case File Comparison →
                </Button>
              </a>
            )}
          </div>
        </Card>

        {/* Privacy note */}
        <p className="text-xs font-mono text-ink-muted text-center">
          🔒 Fiduciary privacy: Your inputs remain in your session. No insurer or broker receives this without explicit consent.
        </p>
      </div>
    </SectionContainer>
  );
}
