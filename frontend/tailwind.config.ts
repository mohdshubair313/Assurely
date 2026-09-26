/**
 * tailwind.config.ts — Assurely Design Tokens (Reference Only)
 *
 * PROJECT_STRUCTURE.md specifies that "Ink/Sky/Paper/Harbor/Clay/Moss
 * tokens live here, nowhere else." However, this project uses
 * Tailwind CSS v4, which replaces JS/TS config files with CSS-first
 * configuration via @theme blocks.
 *
 * ALL TOKENS ARE DEFINED IN: app/globals.css
 *
 * Token mapping (Tailwind utility → CSS variable → design.md source):
 *
 *  bg-canvas        → --canvas         → §4 #F8F5ED / #0E1C24
 *  bg-surface       → --surface        → §4 #FFFDF8 / #142733
 *  bg-surface-raised→ --surface-raised → §4 #FFFFFF / #19313E
 *  text-ink         → --ink            → §4 #14242F / #EEF7F8
 *  text-ink-muted   → --ink-muted      → §4 #5C6A70 / #AABCC1
 *  bg-sky / text-sky→ --sky            → §4 #5BA9D8 / #78C4EF
 *  bg-sky-strong    → --sky-strong     → §4 #187CB8 / #9AD8F5
 *  bg-harbor        → --harbor         → PRD #2C5F73 / #4A8FA8
 *  bg-teal          → --teal           → §4 #187B78 / #70D2C9
 *  bg-moss          → --moss           → PRD #3F6B4A / #6DAF7B
 *  bg-sand          → --sand           → §4 #F0DFC0 / #3D3528
 *  bg-amber         → --amber          → §4 #B96A18 / #FFC36E
 *  bg-clay          → --clay           → PRD #A44A2F / #D4785E
 *  bg-coral         → --coral          → §4 #BC5D54 / #FF9C91
 *  border-line      → --line           → §4 #DCE4E1 / #2B4653
 *  bg-register-sky  → --register-sky   → PRD #EAF1F6 (marketing bg)
 *  bg-register-paper→ --register-paper → PRD #F8F3E9 (product bg)
 *
 *  font-display     → DM Serif Display → §4 (display/hero)
 *  font-body        → Manrope          → §4 (UI/body)
 *  font-mono        → IBM Plex Mono    → §4 (evidence/data)
 *
 *  rounded-input    → 14px             → §4
 *  rounded-card     → 20px             → §4
 *  rounded-hero     → 28px             → §4
 *
 * Do NOT add functional configuration here. If you need to change a
 * token, edit the @theme inline block in app/globals.css.
 */

import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
};

export default config;
