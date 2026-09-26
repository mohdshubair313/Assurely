"use client";
import { useState } from "react";
import Link from "next/link";
import Glyph from "@/components/ui/Glyph";
import ThemeToggle from "@/components/ui/ThemeToggle";
const links = [
  ["How it works", "/#how-it-works"],
  ["What we compare", "/comparison"],
  ["Policy decoder", "/#policy-decoder"],
  ["Audit trail", "/#trust"],
  ["FAQ", "/#faq"],
];
export default function TopNav() {
  const [open, setOpen] = useState(false);
  return <header className="reference-nav">
    <nav className="reference-container nav-inner" aria-label="Main navigation">
      <Link href="/" className="brand"><span className="brand-shield"><Glyph size={25} /></span>Assurely</Link>
      <div className="nav-links">{links.map(([label, href]) => <Link key={href} href={href}>{label}</Link>)}</div>
      <div className="nav-actions"><ThemeToggle /><Link className="sign-in-link" href="/sign-in">Sign in</Link><Link className="pill-button small" href="/intake">Find my cover</Link><button className="mobile-nav-toggle" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="mobile-navigation" aria-label="Toggle navigation">☰</button></div>
    </nav>
    {open && <div id="mobile-navigation" className="mobile-links">{links.map(([label, href]) => <Link key={href} href={href} onClick={() => setOpen(false)}>{label}</Link>)}</div>}
  </header>;
}
