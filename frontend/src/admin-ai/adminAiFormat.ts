/**
 * Display formatting shared by all Admin-AI views.
 */

function finiteNumber(value: unknown): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * Return a display string, or the fallback for empty values.
 */
export function displayText(value: unknown, fallback = "-"): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

/**
 * Format a number for the German UI.
 */
export function numberText(value: unknown): string {
  return finiteNumber(value).toLocaleString("de-DE");
}

/**
 * Format a ratio (0..1) as a whole percent.
 */
export function percentText(value: unknown): string {
  return `${Math.round(finiteNumber(value) * 100)}%`;
}

/**
 * Format an estimated USD amount.
 */
export function moneyText(value: unknown): string {
  return `$${finiteNumber(value).toLocaleString("de-DE", { maximumFractionDigits: 6, minimumFractionDigits: 0 })}`;
}
