import { listData } from "../api/payload";
import { formatGermanDateTime } from "../utils/date";
import { safeErrorMessage } from "../utils/errors";
import { type AdminAiPayload } from "./adminAiApi";
import { ragText, safeJobResultText } from "./adminAiRagBoardModel";
import { moneyText, numberText, percentText } from "./adminAiFormat";

export type AdminAiTechnicalFilters = {
  readonly debugQuery: string;
  readonly debugType: string;
};

export type AdminAiTechnicalState = {
  readonly aiStatus: AdminAiPayload | null;
  readonly errorMessage: string;
  readonly filters: AdminAiTechnicalFilters;
  readonly isLoading: boolean;
  readonly isSaving: boolean;
  readonly jobs: readonly AdminAiPayload[];
  readonly observability: AdminAiPayload | null;
  readonly operations: AdminAiPayload | null;
  readonly retrievalDebug: readonly AdminAiPayload[];
  readonly summary: AdminAiPayload | null;
  readonly telemetry: AdminAiPayload | null;
  readonly statusMessage: string;
};

export const EMPTY_ADMIN_AI_TECHNICAL_STATE: AdminAiTechnicalState = {
  aiStatus: null,
  errorMessage: "",
  filters: { debugQuery: "", debugType: "" },
  isLoading: false,
  isSaving: false,
  jobs: [],
  observability: null,
  operations: null,
  retrievalDebug: [],
  summary: null,
  telemetry: null,
  statusMessage: ""
};

/**
 * Return a query string for retrieval debug.
 */
export function retrievalDebugQueryString(filters: AdminAiTechnicalFilters): string {
  return new URLSearchParams({
    limit: "20",
    q: filters.debugQuery,
    query_type: filters.debugType
  }).toString();
}

/**
 * Return a query string for AI observability.
 */
export function observabilityQueryString(): string {
  return new URLSearchParams({ days: "30", limit: "12" }).toString();
}

/**
 * Return list items from a technical API response.
 */
export function technicalItems(payload: unknown): AdminAiPayload[] {
  return listData<AdminAiPayload>(payload);
}

/**
 * Return a safe Technical state error message.
 */
export function failedTechnicalState(error: unknown): Pick<AdminAiTechnicalState, "errorMessage"> {
  return { errorMessage: safeErrorMessage(error, "Technische Diagnose konnte nicht geladen werden.") };
}

/**
 * Return an object from an unknown payload.
 */
export function objectPayload(value: unknown): AdminAiPayload {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as AdminAiPayload)
    : {};
}

/**
 * Return retrieval SLO values from telemetry.
 */
export function retrievalSloValues(telemetry: AdminAiPayload | null): AdminAiPayload {
  return objectPayload(objectPayload(telemetry?.retrieval_slo).values);
}

/**
 * Format a retrieval SLO value.
 */
export function retrievalSloValue(key: string, value: unknown): string {
  if (key.includes("rate")) return percentText(value);
  if (key.includes("ms")) return `${numberText(value)} ms`;
  return numberText(value);
}

/**
 * Return a label for one metric.
 */
export function metricLabel(key: string): string {
  const labels: Record<string, string> = {
    atlas_errors: "Atlas Fehler",
    atlas_fallbacks: "Atlas Fallbacks",
    atlas_latency: "Atlas Latenz",
    atlas_queries: "Atlas Queries",
    atlas_reindex_required: "Atlas Reindex erforderlich",
    atlas_sync_failures: "Atlas Sync-Fehler",
    atlas_vector_count: "Atlas Vektoren",
    average_response_ms: "Antwortzeit",
    average_retrieval_ms: "Quellenabruf",
    cached_tokens: "Cache Tokens",
    costs: "Kosten",
    empty_retrieval_rate: "Leere Abrufe",
    error_rate: "Fehlerquote",
    fallback_rate: "Ausweichantworten",
    failed_requests: "Fehlgeschlagene Requests",
    governance_alert_count: "Governance Alerts",
    governance_critical_alert_count: "Kritische Governance Alerts",
    governance_status: "Governance Status",
    governance_warning_alert_count: "Governance Warnungen",
    hallucination_warning_count: "Halluzinationswarnungen",
    index_sync_risks: "Index/Sync Risiken",
    latency: "Latenz",
    low_confidence_answers: "Niedrige Sicherheit",
    low_confidence_rate: "Niedrige Sicherheit",
    negative_feedback_rate: "Negatives Feedback",
    no_source_answers: "Antworten ohne Quellen",
    no_source_answer_count: "Beantwortet ohne Quellen",
    no_source_no_data_count: "Keine Daten gefunden",
    no_source_permission_denied_count: "Fehlende Berechtigung",
    no_source_rate: "Ohne Quellen",
    permission_filtered_candidate_count: "Berechtigungsfilter",
    retrieval_hit_rate: "Trefferquote",
    retrieval_p95_ms: "P95 Suchzeit",
    safety_risk_count: "Sicherheitsrisiken",
    source_count_average_answered: "Quellen je beantworteter Frage",
    structured_domain_distribution: "Strukturierte Bereiche",
    successful_requests: "Erfolgreiche Requests",
    token_usage: "Token-Nutzung",
    total_requests: "Requests gesamt",
    total_tokens: "Tokenverbrauch"
  };
  return labels[key] || key;
}

/**
 * Format observability metric values.
 */
export function monitoringValue(key: string, value: unknown): string {
  if (key === "atlas_reindex_required") return value ? "ja" : "nein";
  if (key === "atlas_latency") return `${numberText(value)} ms`;
  if (key.includes("rate") || key.includes("score")) return percentText(value);
  if (key.includes("ms")) return `${numberText(value)} ms`;
  if (key.includes("cost") || key.includes("usd")) return moneyText(value);
  return numberText(value);
}

/**
 * Return a date/time string for technical tables.
 */
export function technicalDateTime(value: unknown): string {
  return formatGermanDateTime(value, { fallback: "-" });
}

/**
 * Return a prompt-safe reference label.
 */
export function technicalReference(prefix: string, id: unknown): string {
  return `${prefix} #${ragText(id, "-")}`;
}

/**
 * Return a selected retrieval debug item.
 */
export function selectedRetrievalDebugItem(items: readonly AdminAiPayload[]): AdminAiPayload | null {
  return items[0] || null;
}

/**
 * Return a compact flow status label.
 */
export function flowStatusLabel(status: unknown): string {
  const key = ragText(status, "");
  const labels: Record<string, string> = {
    blocked: "blockiert",
    empty: "leer",
    filtered: "gefiltert",
    ok: "ok",
    skipped: "übersprungen",
    warning: "Warnung"
  };
  return labels[key] || key || "-";
}

/**
 * Return prompt-safe job rows for technical tables.
 */
export function technicalJobRows(jobs: readonly AdminAiPayload[]): readonly (readonly [unknown, unknown, unknown, unknown, unknown])[] {
  return jobs.map((job) => [
    job.id,
    job.job_type,
    job.status,
    `${ragText(job.attempts, "0")}/${ragText(job.max_attempts, "0")}`,
    safeJobResultText(job)
  ]);
}
