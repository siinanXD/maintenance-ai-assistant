/**
 * Return a safe display string for Admin-AI overview cells.
 */
export function displayText(value: unknown, fallback = "-"): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

/**
 * Format numeric Admin-AI overview values.
 */
export function numberText(value: unknown): string {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed.toLocaleString("de-DE") : displayText(value);
}

