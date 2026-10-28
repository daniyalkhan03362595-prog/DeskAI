/**
 * DeskAI Theme Management (Light / Dark mode toggle & system preference)
 * WCAG 2.1 AA Compliant Palette Switching
 */

import { createSvgIcon } from "./icons.js";

export const THEME_STORAGE_KEY = "deskai_theme";

/**
 * Reads persisted theme from localStorage with try/catch guard.
 * @returns {"light" | "dark" | null}
 */
export function getStoredTheme() {
  try {
    const val = localStorage.getItem(THEME_STORAGE_KEY);
    return val === "light" || val === "dark" ? val : null;
  } catch (err) {
    return null;
  }
}

/**
 * Determines system preferred color scheme.
 * @returns {"light" | "dark"}
 */
export function getSystemTheme() {
  if (typeof window !== "undefined" && window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
    return "light";
  }
  return "dark";
}

/**
 * Sets active theme attribute on :root and optionally persists to localStorage.
 * @param {"light" | "dark"} theme
 * @param {boolean} persist
 * @returns {"light" | "dark"}
 */
export function setTheme(theme, persist = true) {
  const effectiveTheme = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", effectiveTheme);

  if (persist) {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, effectiveTheme);
    } catch (err) {
      // Storage unavailable or disabled
    }
  }

  const toggleBtn = document.getElementById("btnToggleTheme");
  if (toggleBtn) {
    toggleBtn.setAttribute("aria-label", `Current theme: ${effectiveTheme}. Toggle Theme`);
    toggleBtn.replaceChildren(createSvgIcon("theme", 14));
  }

  const announcer = document.getElementById("screenReaderAnnouncer");
  if (announcer) {
    announcer.textContent = `Theme changed to ${effectiveTheme} mode`;
  }

  return effectiveTheme;
}

/**
 * Toggles theme between light and dark.
 * @returns {"light" | "dark"}
 */
export function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || getSystemTheme();
  const next = current === "light" ? "dark" : "light";
  return setTheme(next, true);
}

/**
 * Initializes theme on app startup, syncing with stored or system preference.
 */
export function initTheme() {
  const stored = getStoredTheme();
  const initial = stored || getSystemTheme();
  setTheme(initial, !!stored);

  // Sync with OS preference changes when no explicit override is stored
  if (typeof window !== "undefined" && window.matchMedia) {
    const mql = window.matchMedia("(prefers-color-scheme: light)");
    const handler = (e) => {
      if (!getStoredTheme()) {
        setTheme(e.matches ? "light" : "dark", false);
      }
    };
    if (mql.addEventListener) {
      mql.addEventListener("change", handler);
    } else if (mql.addListener) {
      mql.addListener(handler);
    }
  }

  const toggleBtn = document.getElementById("btnToggleTheme");
  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      toggleTheme();
    });
  }
}
