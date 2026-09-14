const SIDEBAR_COLLAPSED_STORAGE_KEY = "maintenance_sidebar_collapsed";
const HIGH_CONTRAST_STORAGE_KEY = "maintenance_high_contrast";
const THEME_STORAGE_KEY = "maintenance_theme";
const DARK_THEME = "maintenance-dark";
const LIGHT_THEME = "maintenance";

/**
 * Return whether the dark design is active: the stored choice, otherwise the system setting.
 *
 * base.html runs the same check inline before the first paint.
 */
export function readDarkThemePreference(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (stored) {
    return stored === "dark";
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/**
 * Persist and apply the light or dark design.
 */
export function writeDarkThemePreference(isDark: boolean): void {
  window.localStorage.setItem(THEME_STORAGE_KEY, isDark ? "dark" : "light");
  document.documentElement.setAttribute("data-theme", isDark ? DARK_THEME : LIGHT_THEME);
}

/**
 * Read the persisted sidebar collapse preference.
 */
export function readSidebarCollapsedPreference(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === "true";
}

/**
 * Persist the sidebar collapse preference.
 */
export function writeSidebarCollapsedPreference(isCollapsed: boolean): void {
  window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(isCollapsed));
}

/**
 * Read the persisted high contrast preference used by auth.js.
 */
export function readHighContrastPreference(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return window.localStorage.getItem(HIGH_CONTRAST_STORAGE_KEY) === "true";
}

/**
 * Apply the high contrast preference to the document shell.
 */
export function applyHighContrastPreference(isEnabled: boolean): void {
  document.documentElement.classList.toggle("high-contrast", isEnabled);
  document.body.classList.toggle("high-contrast", isEnabled);
}

/**
 * Persist and apply the high contrast preference.
 */
export function writeHighContrastPreference(isEnabled: boolean): void {
  window.localStorage.setItem(HIGH_CONTRAST_STORAGE_KEY, String(isEnabled));
  applyHighContrastPreference(isEnabled);
}
