import { type AdminAiPayload } from "./adminAiApi";
import type { AdminAiStatusCard } from "./adminAiOverviewModel";

/**
 * Return true when a value is a non-array object.
 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Read a nested object field safely.
 */
export function recordField(source: AdminAiPayload | null, key: string): AdminAiPayload {
  const value = source?.[key];
  return isRecord(value) ? value : {};
}

/**
 * Read a string-like field with a fallback.
 */
export function stringField(source: AdminAiPayload | null, key: string, fallback = "-"): string {
  const value = source?.[key];
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

/**
 * Read a numeric field with a fallback.
 */
export function numberField(source: AdminAiPayload | null, key: string, fallback = 0): number {
  const value = source?.[key];
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/**
 * Map Admin-AI health status values to existing CSS tone classes.
 */
export function toneForStatus(status: unknown): AdminAiStatusCard["tone"] {
  const value = String(status ?? "").toLowerCase();
  if (["ok", "ready", "healthy", "active", "success"].includes(value)) return "is-active";
  if (["critical", "error", "failed", "unhealthy"].includes(value)) return "is-error";
  if (["warning", "stale", "degraded", "pending"].includes(value)) return "is-stale";
  return "is-muted";
}
