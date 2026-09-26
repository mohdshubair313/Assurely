/**
 * Theme management — light/dark mode toggle.
 *
 * Uses `data-theme` attribute on <html> to control mode.
 * Reads from localStorage first, falls back to system preference.
 * The CSS in globals.css handles:
 *   - [data-theme="dark"] → dark tokens
 *   - @media (prefers-color-scheme: dark) + :root:not([data-theme="light"]) → system fallback
 */

const STORAGE_KEY = "assurely-theme";

export type Theme = "light" | "dark" | "system";

/** Get the resolved theme (light or dark), accounting for system preference. */
export function getResolvedTheme(): "light" | "dark" {
  if (typeof window === "undefined") return "light";

  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") return stored;

  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

/** Get the user's explicit theme preference (may be "system"). */
export function getThemePreference(): Theme {
  if (typeof window === "undefined") return "system";

  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") return stored;
  return "system";
}

/** Set theme. Pass "system" to remove explicit preference and follow OS. */
export function setTheme(theme: Theme): void {
  if (typeof window === "undefined") return;

  if (theme === "system") {
    localStorage.removeItem(STORAGE_KEY);
    document.documentElement.removeAttribute("data-theme");
  } else {
    localStorage.setItem(STORAGE_KEY, theme);
    document.documentElement.setAttribute("data-theme", theme);
  }
}

/** Toggle between light and dark. */
export function toggleTheme(): void {
  const current = getResolvedTheme();
  setTheme(current === "light" ? "dark" : "light");
}

/**
 * Apply the stored theme on page load.
 * Call this in a client component's useEffect or in an inline <script>.
 */
export function applyStoredTheme(): void {
  if (typeof window === "undefined") return;

  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") {
    document.documentElement.setAttribute("data-theme", stored);
  }
}
