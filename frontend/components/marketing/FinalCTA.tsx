import Button from "@/components/ui/Button";

/**
 * FinalCTA — bottom-of-page call to action.
 *
 * design.md §8.1 section 10:
 * Cream background with blue paper-cut canopy motif.
 * "Bring your questions. Leave with clearer ones."
 */

export default function FinalCTA() {
  return (
    <section className="relative overflow-hidden">
      {/* Background with sky register atmosphere */}
      <div className="absolute inset-0 bg-gradient-to-b from-register-sky via-sky-subtle to-register-sky" />
      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-surface-raised/40 to-transparent" />

      {/* Decorative cloud-like shapes */}
      <div className="absolute top-0 left-1/4 w-96 h-32 bg-surface-raised/20 rounded-full blur-3xl" />
      <div className="absolute bottom-0 right-1/4 w-80 h-28 bg-surface-raised/20 rounded-full blur-3xl" />

      <div className="relative max-w-[1240px] mx-auto px-5 sm:px-8 lg:px-12 py-20 lg:py-28 text-center">
        <h2 className="text-section font-display text-ink mb-4">
          Bring your questions.{" "}
          <br className="hidden sm:block" />
          Leave with clearer ones.
        </h2>

        <p className="text-ink-muted max-w-lg mx-auto mb-8 font-body">
          Insurance decisions are personal. Take five minutes to understand
          what your policy actually says — with no pressure to buy anything.
        </p>

        <a href="/intake" className="inline-block">
          <Button size="lg" variant="primary">
            Find my cover
          </Button>
        </a>

        <p className="mt-4 text-xs font-mono text-ink-muted">
          Takes about 5 minutes · Fiduciary guidance · No phone number needed
        </p>
      </div>
    </section>
  );
}
