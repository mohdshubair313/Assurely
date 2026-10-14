"use client";
import { useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import Glyph from "@/components/ui/Glyph";
import ThemeToggle from "@/components/ui/ThemeToggle";
import styles from "./CelestialHero.module.css";
const links = [
  ["How it works", "/#how-it-works"],
  ["What we compare", "/comparison"],
  ["Policy decoder", "/#policy-decoder"],
  ["Audit trail", "/#trust"],
  ["FAQ", "/#faq"],
];
export default function TopNav() {
  const [open, setOpen] = useState(false);
  const celestial = usePathname() === "/";
  return <header className={celestial ? styles.header : "reference-nav"} onKeyDown={(event) => {
    if (event.key === "Escape") {
      setOpen(false);
      event.currentTarget.querySelector<HTMLButtonElement>("[aria-controls='mobile-navigation']")?.focus();
    }
  }}>
    <nav className={celestial ? styles.nav : "reference-container nav-inner"} aria-label="Main navigation">
      <Link href="/" className={celestial ? styles.brand : "brand"}><span className={celestial ? styles.brandIcon : "brand-shield"}><Glyph size={27} /></span>Assurely</Link>
      <div className={celestial ? styles.links : "nav-links"}>{links.map(([label, href]) => <Link key={href} href={href}>{label}</Link>)}</div>
      <div className={celestial ? styles.navActions : "nav-actions"}>
        <ThemeToggle />
        <Link className={celestial ? styles.signIn : "sign-in-link"} href="/sign-in">Sign in</Link>
        <Link className={celestial ? styles.navCta : "pill-button small"} href="/intake">Find my cover</Link>
        <button className={celestial ? styles.menuButton : "mobile-nav-toggle"} onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="mobile-navigation" aria-label={open ? "Close navigation" : "Open navigation"}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true"><path d={open ? "m6 6 12 12M6 18 18 6" : "M4 8h16M4 16h16"} /></svg>
        </button>
      </div>
    </nav>
    {open && <div id="mobile-navigation" className={celestial ? styles.mobileMenu : "mobile-links"}>
      {links.map(([label, href]) => <Link key={href} href={href} onClick={() => setOpen(false)}>{label}</Link>)}
      {celestial && <><Link href="/sign-in" onClick={() => setOpen(false)}>Sign in</Link><Link href="/intake" onClick={() => setOpen(false)}>Find my cover <Glyph name="arrow" size={16} /></Link></>}
    </div>}
  </header>;
}
