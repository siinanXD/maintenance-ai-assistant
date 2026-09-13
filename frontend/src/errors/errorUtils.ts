import { formatGermanDateTime } from "../utils/date";
import { safeErrorMessage } from "../utils/errors";
import type { ErrorDraft, ErrorEntry, ErrorFilters, ErrorSeverity, ErrorStatus } from "./errorTypes";

export const ERROR_CATEGORIES = [
  "Elektrik",
  "Mechanik",
  "Pneumatik",
  "Hydraulik",
  "SPS/Software",
  "Sensorik",
  "Netzwerk",
  "Bedienfehler",
  "Sonstiges"
] as const;

export const QUICK_FILTERS = ["Elektrik", "Mechanik", "Hydraulik", "SPS/Software", "Sensorik", "Netzwerk"] as const;

/**
 * Create an empty error form draft.
 */
export function createEmptyErrorDraft(): ErrorDraft {
  return {
    department: "",
    machine: "",
    error_code: "",
    status: "open",
    severity: "medium",
    cause_category: "",
    title: "",
    symptoms: "",
    possible_causes: "",
    solution: "",
    impact: "",
    downtime_minutes: "",
    production_loss_minutes: "",
    repeat_count: ""
  };
}

/**
 * Convert an existing error entry to an editable draft.
 */
export function draftFromError(entry: ErrorEntry): ErrorDraft {
  return {
    department: entry.department?.name || "",
    machine: entry.machine || "",
    error_code: entry.error_code || "",
    status: normalizeStatus(entry.status),
    severity: normalizeSeverity(entry.severity),
    cause_category: entry.cause_category || "",
    title: entry.title || "",
    symptoms: entry.symptoms || entry.description || "",
    possible_causes: entry.possible_causes || "",
    solution: entry.solution || "",
    impact: entry.impact || "",
    downtime_minutes: stringValue(entry.downtime_minutes),
    production_loss_minutes: stringValue(entry.production_loss_minutes),
    repeat_count: stringValue(entry.repeat_count)
  };
}

/**
 * Merge analysis data into a complete form draft.
 */
export function draftFromAnalysis(analysis: Partial<ErrorDraft>, currentDepartment: string): ErrorDraft {
  return {
    ...createEmptyErrorDraft(),
    department: analysis.department || currentDepartment,
    machine: analysis.machine || "",
    error_code: analysis.error_code || "NEU",
    title: analysis.title || "",
    symptoms: analysis.symptoms || "",
    possible_causes: analysis.possible_causes || "",
    solution: analysis.solution || ""
  };
}

/**
 * Return the initial search query from URL parameters.
 */
export function initialErrorSearchQuery(): string {
  const query = new URLSearchParams(window.location.search);
  return query.get("search") || query.get("q") || "";
}

/**
 * Resolve a user-facing error message.
 */
export function errorMessage(error: unknown): string {
  return safeErrorMessage(error, "Die Anfrage konnte nicht verarbeitet werden.");
}

/**
 * Return a localized status label.
 */
export function errorStatusLabel(status: unknown): string {
  const labels: Record<string, string> = {
    open: "Offen",
    in_progress: "In Bearbeitung",
    closed: "Geschlossen"
  };
  return labels[String(status || "open")] || "Offen";
}

/**
 * Return a localized severity label.
 */
export function errorSeverityLabel(severity: unknown): string {
  const labels: Record<string, string> = {
    critical: "Kritisch",
    high: "Hoch",
    medium: "Mittel",
    low: "Niedrig"
  };
  return labels[String(severity || "medium")] || "Mittel";
}

/**
 * Return the CSS class for an error status badge.
 */
export function errorStatusClass(status: unknown): string {
  if (status === "closed") return "badge status-badge is-done";
  if (status === "in_progress") return "badge status-badge is-progress";
  return "badge status-badge is-open";
}

/**
 * Return the CSS class for an error severity badge.
 */
export function errorSeverityClass(severity: unknown): string {
  if (severity === "critical") return "badge priority-badge is-urgent";
  if (severity === "high") return "badge priority-badge is-soon";
  if (severity === "low") return "badge priority-badge is-normal";
  return "badge priority-badge is-medium";
}

/**
 * Format minutes as "35 min" or, from one hour, as "1,5 h".
 */
export function formatIncidentMinutes(value: unknown): string {
  const minutes = Number(value || 0);
  if (minutes >= 60) return `${(minutes / 60).toFixed(1).replace(".", ",")} h`;
  return `${Math.round(minutes)} min`;
}

/**
 * Format an incident timestamp as day, month and time.
 */
export function incidentDate(value: unknown): string {
  return formatGermanDateTime(value, {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    fallback: "-"
  });
}

/**
 * Build the searchable plain text for one error entry.
 */
function incidentSearchText(entry: ErrorEntry): string {
  return [
    entry.error_code,
    entry.machine,
    entry.title,
    entry.description,
    entry.symptoms,
    entry.possible_causes,
    entry.solution,
    entry.department?.name,
    entry.status,
    errorStatusLabel(entry.status),
    entry.severity,
    errorSeverityLabel(entry.severity),
    entry.cause_category,
    entry.impact
  ].filter(Boolean).join(" ").toLowerCase();
}

/**
 * Return whether an error matches all active filters.
 */
export function errorMatchesFilters(entry: ErrorEntry, filters: ErrorFilters): boolean {
  const searchText = incidentSearchText(entry);
  if (filters.quick && filters.quick !== "all" && !errorMatchesQuickFilter(entry, filters.quick, searchText)) return false;
  if (filters.status && (entry.status || "open") !== filters.status) return false;
  if (filters.severity && (entry.severity || "medium") !== filters.severity) return false;
  if (filters.category && (entry.cause_category || "") !== filters.category) return false;
  if (!filters.search.trim()) return true;
  return searchText.includes(filters.search.trim().toLowerCase());
}

/**
 * Return the category options visible in loaded errors.
 */
export function categoriesFromErrors(errors: readonly ErrorEntry[]): string[] {
  return Array.from(new Set(errors.map((entry) => entry.cause_category).filter((category): category is string => Boolean(category))))
    .sort((first, second) => first.localeCompare(second, "de-DE"));
}

/**
 * Normalize a maybe-status value.
 */
function normalizeStatus(status: unknown): ErrorStatus {
  return ["open", "in_progress", "closed"].includes(String(status)) ? String(status) as ErrorStatus : "open";
}

/**
 * Normalize a maybe-severity value.
 */
function normalizeSeverity(severity: unknown): ErrorSeverity {
  return ["critical", "high", "medium", "low"].includes(String(severity)) ? String(severity) as ErrorSeverity : "medium";
}

/**
 * Convert optional numeric fields to form strings.
 */
function stringValue(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

/**
 * Return whether one entry matches a quick category filter.
 */
function errorMatchesQuickFilter(entry: ErrorEntry, filterName: string, searchText: string): boolean {
  if ((entry.cause_category || "").toLowerCase() === filterName.toLowerCase()) return true;
  return searchText.includes(filterName.toLowerCase());
}
