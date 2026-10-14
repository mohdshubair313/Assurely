"use client";

import { useEffect, useRef, type ReactNode } from "react";

/** One-time, progressively enhanced reveals; content stays visible without JS. */
export default function LandingMotion({ children, className }: { children: ReactNode; className: string }) {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (preference.matches || !root.current) return;
    const animations = new Set<Animation>();
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        observer.unobserve(entry.target);
        if (preference.matches) return;
        const animation = entry.target.animate(
          [{ opacity: 0.35, transform: "translateY(18px)" }, { opacity: 1, transform: "translateY(0)" }],
          { duration: 550, easing: "cubic-bezier(.22, 1, .36, 1)" },
        );
        animations.add(animation);
        animation.finished.then(() => animations.delete(animation)).catch(() => {});
      });
    }, { threshold: 0.12 });
    root.current.querySelectorAll("[data-reveal]").forEach((node) => observer.observe(node));
    const stopMotion = () => { if (preference.matches) animations.forEach((animation) => animation.cancel()); };
    preference.addEventListener("change", stopMotion);
    return () => { observer.disconnect(); preference.removeEventListener("change", stopMotion); animations.forEach((animation) => animation.cancel()); };
  }, []);
  return <div ref={root} className={className}>{children}</div>;
}
