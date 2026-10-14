"use client";

import { useRef, type ReactNode } from "react";
import styles from "./LandingExperience.module.css";

/** A separate composite layer catches light without moving readable content. */
export default function ReflectiveSurface({ children, className }: { children: ReactNode; className: string }) {
  const sheen = useRef<HTMLSpanElement>(null);
  return <div className={`${className} ${styles.reflectiveSurface}`} onPointerMove={event => {
    if (event.pointerType !== "mouse" || !sheen.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
    sheen.current.style.transform = `translate3d(${(x - .5) * rect.width * .65}px, ${(y - .5) * rect.height * .65}px, 0)`;
  }} onPointerLeave={() => { if (sheen.current) sheen.current.style.transform = "translate3d(0,0,0)"; }}>
    <span ref={sheen} className={styles.surfaceSheen} aria-hidden="true" />{children}
  </div>;
}
