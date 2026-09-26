import type { Metadata } from "next";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";

/**
 * Sign-in page — from Stitch export.
 *
 * design.md §8.2:
 * Split-screen desktop: warm cream content side + small framed canopy scene.
 * Title: "Continue your insurance workspace"
 * Security note: "We ask permission before storing information..."
 * Never include a broad marketing consent checkbox preselected.
 */

export const metadata: Metadata = {
  title: "Sign In — Assurely",
  description:
    "Continue your insurance workspace. We ask permission before storing information used in your comparison.",
};

export default function SignInPage() {
  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex">
      {/* Left — sign-in form */}
      <div className="flex-1 flex items-center justify-center px-5 sm:px-8 lg:px-12 py-12">
        <div className="w-full max-w-md space-y-8">
          <div>
            <h1 className="text-section font-display text-ink mb-2">
              Continue your insurance workspace
            </h1>
            <p className="text-ink-muted font-body">
              Sign in to start or resume your health insurance comparison.
            </p>
          </div>

          {/* Form */}
          <Card variant="raised" className="p-6 lg:p-8 shadow-card">
            <form className="space-y-5">
              {/* Email */}
              <div>
                <label
                  htmlFor="email"
                  className="block text-sm font-medium font-body text-ink mb-1.5"
                >
                  Email address
                </label>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  className="w-full px-4 py-2.5 rounded-input border border-line bg-surface text-ink
                             placeholder:text-ink-muted font-body
                             focus:outline-none focus:ring-2 focus:ring-harbor focus:border-harbor
                             transition-theme"
                  placeholder="you@example.com"
                />
              </div>

              {/* Password */}
              <div>
                <label
                  htmlFor="password"
                  className="block text-sm font-medium font-body text-ink mb-1.5"
                >
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  className="w-full px-4 py-2.5 rounded-input border border-line bg-surface text-ink
                             placeholder:text-ink-muted font-body
                             focus:outline-none focus:ring-2 focus:ring-harbor focus:border-harbor
                             transition-theme"
                  placeholder="••••••••"
                />
              </div>

              <Button type="submit" variant="primary" className="w-full">
                Sign in
              </Button>

              <div className="relative my-4">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-line" />
                </div>
                <div className="relative flex justify-center text-xs font-mono">
                  <span className="bg-surface-raised px-3 text-ink-muted">
                    or
                  </span>
                </div>
              </div>

              <Button variant="secondary" type="button" className="w-full">
                Send magic link to email
              </Button>
            </form>
          </Card>

          {/* Security note */}
          <div className="flex items-start gap-2.5 p-3 rounded-card bg-moss-subtle border border-moss/30 text-xs font-body">
            <svg
              className="w-4 h-4 text-moss flex-shrink-0 mt-0.5"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z"
              />
            </svg>
            <p className="text-ink-muted leading-relaxed">
              We ask permission before storing information used in your
              comparison. No marketing consent is preselected (DPDP Act compliant).
            </p>
          </div>

          {/* Create account link */}
          <p className="text-center text-sm font-body text-ink-muted">
            No account yet?{" "}
            <a href="/sign-in" className="text-harbor hover:text-harbor-strong transition-theme font-medium">
              Create one
            </a>
          </p>
        </div>
      </div>

      {/* Right — decorative scene (desktop only) */}
      <div className="hidden lg:flex lg:w-2/5 bg-register-sky items-center justify-center p-12">
        <div className="w-full max-w-sm aspect-square rounded-hero bg-gradient-to-b from-sky-subtle to-register-sky flex items-center justify-center border border-line">
          <div className="text-center space-y-3 p-8">
            <div className="w-14 h-14 mx-auto rounded-full bg-surface border border-line flex items-center justify-center text-harbor shadow-sm">
              <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 12 8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
              </svg>
            </div>
            <p className="text-base text-ink font-display italic">
              Your coverage, understood.
            </p>
            <p className="text-xs font-mono text-ink-muted">
              Independent Case File Dossier
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
