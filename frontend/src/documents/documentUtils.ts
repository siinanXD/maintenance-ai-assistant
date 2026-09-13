import { formatGermanDateTime } from "../utils/date";
import { triggerBrowserDownload } from "../utils/download";
import { safeErrorMessage } from "../utils/errors";
import type { DocumentFilters, GeneratedDocument } from "./documentTypes";

/**
 * Return empty document filters.
 */
export function emptyDocumentFilters(): DocumentFilters {
  return {
    task_id: "",
    department: "",
    machine: "",
    date_from: "",
    date_to: ""
  };
}

/**
 * Resolve a safe user-facing error message.
 */
export function documentErrorMessage(error: unknown): string {
  return safeErrorMessage(error, "Dokumentaktion konnte nicht verarbeitet werden.");
}

/**
 * Return localized document approval status text.
 */
export function documentStatusText(value: unknown): string {
  if (value === "in_review") return "In Prüfung";
  if (value === "approved") return "Freigegeben";
  if (value === "rejected") return "Abgelehnt";
  return "Entwurf";
}

/**
 * Return localized review status text.
 */
export function reviewStatusText(status: unknown): string {
  if (status === "good") return "Gut";
  if (status === "needs_review") return "Prüfen";
  return "Unvollständig";
}

/**
 * Return a status badge class.
 */
export function statusBadgeClass(value: unknown): string {
  if (value === "approved" || value === "ready" || value === "good") return "badge badge-status is-done";
  if (value === "in_review" || value === "needs_review") return "badge badge-status is-progress";
  return "badge badge-status is-open";
}

/**
 * Return a localized date-time label.
 */
export function dateTimeLabel(value: unknown): string {
  return formatGermanDateTime(value, { fallback: "-" });
}

/**
 * Trigger a browser download for an existing API file URL.
 */
export function triggerDownload(url: string | undefined, filename: string): void {
  triggerBrowserDownload(url, filename);
}

/**
 * Return searchable text for a generated document.
 */
export function generatedDocumentSearchText(document: GeneratedDocument): string {
  return [
    document.title,
    document.task_id,
    document.department,
    document.machine,
    documentStatusText(document.status)
  ].filter(Boolean).join(" ").toLowerCase();
}

