import { formatGermanDateTime } from "../utils/date";
import { safeErrorMessage } from "../utils/errors";
import { type AdminAiPayload } from "./adminAiApi";
export { capabilityGroups } from "./adminAiCapabilityModel";

type AdminAiUserCostRow = {
  readonly estimated_cost_usd?: unknown;
  readonly events?: unknown;
  readonly fallback_rate?: unknown;
  readonly langfuse_user_id?: unknown;
  readonly latest_used_at?: unknown;
  readonly total_tokens?: unknown;
  readonly username?: unknown;
};

export type AdminAiEffectivenessState = {
  readonly summary: AdminAiPayload | null;
  readonly telemetry: AdminAiPayload | null;
  readonly userCosts: readonly AdminAiUserCostRow[];
  readonly errorMessage: string;
  readonly isLoading: boolean;
};

export type AdminAiMetricRow = {
  readonly label: string;
  readonly value: string;
};

export type AdminAiBarRow = AdminAiMetricRow & {
  readonly width: string;
};

export type AdminAiCapabilityGroup = {
  readonly key: "partial" | "supported" | "unsupported";
  readonly items: readonly AdminAiMetricRow[];
  readonly tone: "is-active" | "is-muted" | "is-stale";
};

export const EMPTY_ADMIN_AI_EFFECTIVENESS_STATE: AdminAiEffectivenessState = {
  summary: null,
  telemetry: null,
  userCosts: [],
  errorMessage: "",
  isLoading: true
};

/**
 * Return true when a value is an object payload.
 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Return a nested object field or an empty object.
 */
function recordField(source: AdminAiPayload | null, key: string): AdminAiPayload {
  const value = source?.[key];
  return isRecord(value) ? value : {};
}

/**
 * Return a nested list field or an empty list.
 */
function listField<TItem>(source: AdminAiPayload | null, key: string): TItem[] {
  const value = source?.[key];
  return Array.isArray(value) ? (value as TItem[]) : [];
}

/**
 * Convert a value to a stable UI string.
 */
function text(value: unknown, fallback = "-"): string {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

/**
 * Convert a value to a finite number.
 */
function numeric(value: unknown): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * Format a plain number for German UI.
 */
export function numberText(value: unknown): string {
  return numeric(value).toLocaleString("de-DE");
}

/**
 * Format a ratio as whole percent.
 */
export function percentText(value: unknown): string {
  return `${Math.round(numeric(value) * 100)}%`;
}

/**
 * Format an estimated USD value like the legacy Admin-AI views.
 */
export function moneyText(value: unknown): string {
  return `$${numeric(value).toLocaleString("de-DE", {
    maximumFractionDigits: 6,
    minimumFractionDigits: 0
  })}`;
}

/**
 * Return the retrieval SLO values from either old or new backend shape.
 */
function retrievalSloValues(state: AdminAiEffectivenessState): AdminAiPayload {
  const retrievalSlo = recordField(state.telemetry, "retrieval_slo");
  const values = recordField(retrievalSlo, "values");
  if (Object.keys(values).length) return values;
  return recordField(retrievalSlo, "last_values");
}

/**
 * Format a summary KPI by key.
 */
export function effectivenessKpiValue(state: AdminAiEffectivenessState, key: string): string {
  const value = state.summary?.[key];
  if (key.includes("cost") || key.includes("usd")) return moneyText(value);
  if (key.includes("rate")) return percentText(value);
  return numberText(value);
}

/**
 * Return price-configuration status text.
 */
export function priceStatusText(state: AdminAiEffectivenessState): string {
  const priceConfiguration = recordField(state.summary, "price_configuration");
  return priceConfiguration.configured ? "konfiguriert" : "AI_PRICE_* fehlen - Kosten bleiben 0,00";
}

/**
 * Return Langfuse metrics from the summary payload.
 */
export function langfuseMetricValue(state: AdminAiEffectivenessState, key: string): string {
  const metrics = recordField(state.summary, "langfuse_metrics");
  const value = metrics[key];
  if (key.includes("cost")) return moneyText(value);
  return numberText(value);
}

/**
 * Return the Langfuse availability badge.
 */
export function langfuseStatus(state: AdminAiEffectivenessState): AdminAiMetricRow & { tone: string } {
  const metrics = recordField(state.summary, "langfuse_metrics");
  const available = Boolean(metrics.available);
  return {
    label: available ? "Langfuse geladen" : text(metrics.message, "Nicht verfügbar"),
    value: available ? "Langfuse geladen" : text(metrics.message, "Nicht verfügbar"),
    tone: available ? "is-active" : "is-stale"
  };
}

/**
 * Build proportional mini-bar rows.
 */
function barRows(items: readonly AdminAiPayload[], labelKey: string, valueKey: string): AdminAiBarRow[] {
  const maxValue = Math.max(...items.map((item) => numeric(item[valueKey])), 0.000001);
  return items.map((item) => ({
    label: text(item[labelKey], "unbekannt"),
    value:
      valueKey === "estimated_cost_usd" || valueKey === "total_cost_usd"
        ? moneyText(item[valueKey])
        : numberText(item[valueKey]),
    width: `${Math.max(4, (numeric(item[valueKey]) / maxValue) * 100)}%`
  }));
}

/**
 * Return Langfuse model cost rows.
 */
export function langfuseModelRows(state: AdminAiEffectivenessState): AdminAiBarRow[] {
  const metrics = recordField(state.summary, "langfuse_metrics");
  return barRows(listField<AdminAiPayload>(metrics, "models").slice(0, 8), "model", "total_cost_usd");
}

/**
 * Return Langfuse workflow cost rows.
 */
export function langfuseWorkflowRows(state: AdminAiEffectivenessState): AdminAiBarRow[] {
  const metrics = recordField(state.summary, "langfuse_metrics");
  return barRows(listField<AdminAiPayload>(metrics, "workflows").slice(0, 8), "workflow", "total_cost_usd");
}

/**
 * Return workflow cost chart rows.
 */
export function workflowCostRows(state: AdminAiEffectivenessState): AdminAiBarRow[] {
  return barRows(
    listField<AdminAiPayload>(state.summary, "top_workflows").slice(0, 6),
    "workflow",
    "estimated_cost_usd"
  );
}

/**
 * Return helpful feedback rate as text.
 */
export function helpfulRateText(state: AdminAiEffectivenessState): string {
  const feedback = recordField(state.summary, "feedback");
  return percentText(feedback.helpful_rate);
}

/**
 * Return effectiveness risk rows.
 */
export function effectivenessRiskRows(state: AdminAiEffectivenessState): AdminAiMetricRow[] {
  const values = retrievalSloValues(state);
  return [
    { label: "Ohne Quellen", value: percentText(values.no_source_rate) },
    { label: "Negatives Feedback", value: percentText(values.negative_feedback_rate) },
    { label: "Niedrige Sicherheit", value: percentText(values.low_confidence_rate) },
    {
      label: "Fallback-Rate",
      value: percentText(state.summary?.fallback_rate ?? values.fallback_rate)
    }
  ];
}

/**
 * Return safety snapshot field values.
 */
export function safetyFields(state: AdminAiEffectivenessState): AdminAiMetricRow[] {
  const values = retrievalSloValues(state);
  return [
    { label: "fallback_rate", value: percentText(state.summary?.fallback_rate ?? values.fallback_rate) },
    { label: "safety_risk_count", value: numberText(values.safety_risk_count) },
    { label: "no_source_rate", value: percentText(values.no_source_rate) },
    { label: "low_confidence_rate", value: percentText(values.low_confidence_rate) }
  ];
}

/**
 * Return the safety panel status.
 */
export function safetyStatus(state: AdminAiEffectivenessState): AdminAiMetricRow & { tone: string } {
  const values = retrievalSloValues(state);
  const safetyRiskCount = numeric(values.safety_risk_count);
  const noSourceRate = numeric(values.no_source_rate);
  const lowConfidenceRate = numeric(values.low_confidence_rate);
  const fallbackRate = numeric(state.summary?.fallback_rate ?? values.fallback_rate);
  const critical =
    safetyRiskCount >= 5 || noSourceRate >= 0.4 || lowConfidenceRate >= 0.4 || fallbackRate >= 0.5;
  const warning =
    !critical &&
    (safetyRiskCount > 0 || noSourceRate >= 0.2 || lowConfidenceRate >= 0.2 || fallbackRate >= 0.2);
  return {
    label: critical ? "Handlungsbedarf" : warning ? "Beobachten" : "unauffällig",
    value: critical ? "Handlungsbedarf" : warning ? "Beobachten" : "unauffällig",
    tone: critical ? "is-error" : warning ? "is-stale" : "is-active"
  };
}

/**
 * Normalize the user-cost API response into rows.
 */
export function userCostRows(payload: AdminAiPayload | null): AdminAiUserCostRow[] {
  return listField<AdminAiUserCostRow>(payload, "items");
}

/**
 * Format one user-cost table cell by key.
 */
export function userCostCell(row: AdminAiUserCostRow, key: keyof AdminAiUserCostRow): string {
  if (key === "estimated_cost_usd") return moneyText(row[key]);
  if (key === "fallback_rate") return percentText(row[key]);
  if (key === "latest_used_at") return formatGermanDateTime(row[key], { fallback: "-" });
  return text(row[key]);
}

/**
 * Convert a partial load failure into a safe status message.
 */
export function failedEffectivenessState(error: unknown): Pick<AdminAiEffectivenessState, "errorMessage"> {
  return {
    errorMessage: safeErrorMessage(error, "AI-Admin Effektivität konnte nicht komplett geladen werden.")
  };
}
