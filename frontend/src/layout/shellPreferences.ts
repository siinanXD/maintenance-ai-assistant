const SIDEBAR_COLLAPSED_STORAGE_KEY = "maintenance_sidebar_collapsed";
const HIGH_CONTRAST_STORAGE_KEY = "maintenance_high_contrast";

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
