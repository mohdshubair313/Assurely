import type { Metadata } from "next";
import SectionContainer from "@/components/ui/SectionContainer";

/**
 * How It Works page — stub.
 *
 * Content deferred — placeholder with heading and section structure.
 */

export const metadata: Metadata = {
  title: "How It Works — Assurely",
  description:
    "Learn how Assurely translates policy terms, compares trade-offs, and helps you decide — in minutes, not months.",
};

export default function HowItWorksPage() {
  return (
    <SectionContainer className="py-16 lg:py-24">
      <h1 className="text-section font-display text-ink mb-6">
        How it works
      </h1>
      <p className="text-ink-muted max-w-xl leading-relaxed">
        This page will explain the Assurely process in detail. Content coming
        soon — see the landing page for a quick overview.
      </p>
    </SectionContainer>
  );
}
