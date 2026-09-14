import { formatGermanDateTime } from "../utils/date";
import { ragText } from "./adminAiRagBoardModel";

/**
 * Return the label for one source type.
 */
export function sourceTypeLabel(sourceType: unknown): string {
  const labels: Record<string, string> = {
    error_entry: "Fehlerkatalog",
    faq: "FAQ",
    generated_document: "Berichte",
    inventory_material: "Inventar",
    machine: "Maschinen",
    machine_manual: "Maschineninfos",
    maintenance_plan: "Wartungspläne",
    manual_training: "Manuelles Training",
    shift_handover: "Schichtübergaben",
    task: "Aufgaben",
    upload: "Uploads"
  };
  const key = ragText(sourceType, "");
  return labels[key] || key || "-";
}

/**
 * Return the label for one editorial quality status.
 */
export function qualityStatusLabel(status: unknown): string {
  const labels: Record<string, string> = {
    admin_approved: "Admin freigegeben",
    ai_suggested: "AI-Vorschlag",
    draft: "Entwurf",
    duplicate: "Duplikat",
    low_quality: "Niedrige Qualität",
    outdated: "Veraltet",
    rejected: "Abgelehnt",
    technician_confirmed: "Techniker bestätigt"
  };
  const key = ragText(status, "draft");
  return labels[key] || key;
}

/**
 * Return the status pill class for one quality status.
 */
export function qualityStatusClass(status: unknown): string {
  const key = ragText(status, "draft");
  if (key === "admin_approved" || key === "technician_confirmed") return "is-active";
  if (key === "outdated" || key === "low_quality" || key === "duplicate") return "is-stale";
  if (key === "rejected") return "is-error";
  return "is-muted";
}

/**
 * Return a date/time label for RAG admin tables.
 */
export function ragDateTime(value: unknown): string {
  return formatGermanDateTime(value, { fallback: "-" });
}

/**
 * Return the label for one knowledge network node type.
 */
export function networkTypeLabel(type: unknown): string {
  const labels: Record<string, string> = {
    component: "Komponente",
    document: "Dokument",
    error: "Fehler",
    inventory_part: "Inventar",
    knowledge_gap: "Wissenslücke",
    machine: "Maschine",
    recurring_issue: "Wiederkehrender Fehler",
    sensor: "Sensor",
    solution: "Lösung",
    task: "Aufgabe"
  };
  const key = ragText(type, "");
  return labels[key] || key || "-";
}

/**
 * Return a shortened label for dense network chips.
 */
export function truncateLabel(value: unknown, maxLength = 52): string {
  const label = ragText(value, "");
  if (label.length <= maxLength) return label;
  return `${label.slice(0, maxLength - 3).trim()}...`;
}
