"use client";
import Glyph from "./Glyph";
export default function ThemeToggle() {
  function toggleTheme() {
    const root = document.documentElement;
    const theme = root.dataset.theme === "dark" ? "light" : "dark";
    root.dataset.theme = theme;
    try { localStorage.setItem("assurely-theme", theme); } catch { /* Theme works without storage. */ }
  }
  return <button className="theme-toggle" onClick={toggleTheme} aria-label="Toggle color theme" title="Switch light / dark appearance"><Glyph name="moon" size={18} /></button>;
}
