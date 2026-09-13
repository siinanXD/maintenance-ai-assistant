import { safeErrorMessage } from "../utils/errors";
import { type AdminAiPayload } from "./adminAiApi";
import {
  moneyText,
  numberField,
  numberText,
  percentText,
  recordField,
  stringField,
  toneForStatus
} from "./adminAiOverviewHelpers";

export type AdminAiOverviewLoadState = {
  readonly aiStatus: AdminAiPayload | null;
  readonly chats: readonly AdminAiPayload[];
  readonly events: readonly AdminAiPayload[];
  readonly summary: AdminAiPayload | null;
  readonly operations: AdminAiPayload | null;
  readonly errorMessage: string;
  readonly isLoading: boolean;
};

export type AdminAiStatusCard = {
  readonly key: string;
  readonly label: string;
  readonly value: string;
  readonly detail: string;
  readonly tone: "is-active" | "is-stale" | "is-error" | "is-muted";
};

export type AdminAiHealthCard = {
  readonly key: string;
  readonly label: string;
  readonly detail: string;
  readonly tone: "is-active" | "is-stale" | "is-error" | "is-muted";
};

export type AdminAiProviderField = {
  readonly key: string;
  readonly label: string;
  readonly value: string;
  readonly detail: string;
};

export type AdminAiStatRow = {
  readonly label: string;
  readonly value: string;
};

export type AdminAiActionItem = {
  readonly detail: string;
  readonly key: string;
  readonly label: string;
  readonly tone: "is-active" | "is-stale" | "is-error" | "is-muted";
};

export const EMPTY_ADMIN_AI_OVERVIEW_STATE: AdminAiOverviewLoadState = {
  aiStatus: null,
  chats: [],
  events: [],
  summary: null,
  operations: null,
  errorMessage: "",
  isLoading: true
};

/**
 * Build the main overview status badge text from partial API payloads.
 */
export function overviewBadge(state: AdminAiOverviewLoadState): AdminAiStatusCard {
  const ready = state.aiStatus ? state.aiStatus.ready !== false : true;
  const summaryReadiness = recordField(state.summary, "readiness");
  const readinessStatus = stringField(summaryReadiness, "status", ready ? "ok" : "critical");
  const tone = state.errorMessage ? "is-stale" : toneForStatus(readinessStatus);
  const label = state.errorMessage
    ? "Teilweise geladen"
    : tone === "is-error"
      ? "Handlungsbedarf"
      : tone === "is-stale"
        ? "Beobachten"
        : state.isLoading
          ? "Wird geladen"
          : "Betriebsbereit";
  return {
    key: "overview",
    label,
    value: label,
    detail: state.errorMessage || "AI-Status, Summary und Operations-Metriken",
    tone: state.isLoading ? "is-muted" : tone
  };
}

/**
 * Build the four compact status cards for quick fault detection.
 */
export function overviewCriticalCards(state: AdminAiOverviewLoadState): AdminAiStatusCard[] {
  const aiReady = state.aiStatus ? state.aiStatus.ready !== false : false;
  const readiness = recordField(state.summary, "readiness");
  const retrievalQuality = recordField(state.summary, "retrieval_quality");
  const operationsJobs = recordField(state.operations, "background_jobs");
  const provider = stringField(state.aiStatus, "provider", "unbekannt");
  const model = stringField(state.aiStatus, "model", "unbekannt");
  const noSourceRate = numberField(retrievalQuality, "no_source_rate");
  const failedJobs = numberField(operationsJobs, "failed");
  const queuedJobs = numberField(operationsJobs, "queue_length");
  const ragStatus = stringField(readiness, "status", state.isLoading ? "wird geladen" : "offen");

  return [
    {
      key: "ready",
      label: "Gesamtstatus",
      value: state.errorMessage ? "Teilweise" : aiReady ? "bereit" : "prüfen",
      detail: state.errorMessage || `${provider} / ${model}`,
      tone: state.errorMessage ? "is-stale" : aiReady ? "is-active" : "is-error"
    },
    {
      key: "rag",
      label: "RAG",
      value: ragStatus,
      detail: stringField(readiness, "reasons", "Index und Quellenbereitschaft"),
      tone: toneForStatus(readiness.status)
    },
    {
      key: "no_source",
      label: "Ohne Quellen",
      value: percentText(noSourceRate),
      detail: noSourceRate >= 0.2 ? "Schwellenwert kritisch" : "Antwortqualität im Zielbereich",
      tone: noSourceRate >= 0.4 ? "is-error" : noSourceRate >= 0.2 ? "is-stale" : "is-active"
    },
    {
      key: "jobs",
      label: "Hintergrundjobs",
      value: failedJobs ? "fehlgeschlagen" : queuedJobs ? "wartend" : "ruhig",
      detail: `${numberText(queuedJobs)} wartend / ${numberText(failedJobs)} fehlgeschlagen`,
      tone: failedJobs ? "is-error" : queuedJobs ? "is-stale" : "is-active"
    }
  ];
}

/**
 * Build the five compact status cards from the overview payloads.
 */
export function overviewStatusCards(state: AdminAiOverviewLoadState): AdminAiStatusCard[] {
  const aiReady = state.aiStatus ? state.aiStatus.ready !== false : false;
  const provider = stringField(state.aiStatus, "provider", "lokal");
  const model = stringField(state.aiStatus, "model", "lokal");
  const fallbackRate = numberField(state.summary, "fallback_rate");
  const operationsJobs = recordField(state.operations, "background_jobs");
  const queuedJobs = numberField(operationsJobs, "queue_length");
  const failedJobs = numberField(operationsJobs, "failed");

  return [
    {
      key: "ai",
      label: "AI",
      value: state.aiStatus ? (aiReady ? "aktiv" : "inaktiv") : "Wird geladen",
      detail: state.aiStatus ? "Anbieterstatus aus /api/v1/ai/status" : "Status wird geladen",
      tone: state.aiStatus ? (aiReady ? "is-active" : "is-error") : "is-muted"
    },
    {
      key: "openai",
      label: "OpenAI",
      value: provider.toLowerCase().includes("openai") || model.toLowerCase().includes("gpt")
        ? "konfiguriert"
        : "nicht konfiguriert",
      detail: `${provider} / ${model}`,
      tone: state.aiStatus ? (aiReady ? "is-active" : "is-error") : "is-muted"
    },
    {
      key: "fallback",
      label: "Lokaler Ausweichbetrieb",
      value: fallbackRate > 0 || !aiReady ? "aktiv" : "inaktiv",
      detail: `Fallback-Rate ${percentText(fallbackRate)}`,
      tone: fallbackRate > 0 || !aiReady ? "is-stale" : "is-active"
    },
    {
      key: "rag",
      label: "RAG",
      value: stringField(recordField(state.summary, "readiness"), "status", "wird geladen"),
      detail: "Bereitschaft aus Admin-AI-Summary",
      tone: toneForStatus(recordField(state.summary, "readiness").status)
    },
    {
      key: "reindex",
      label: "Letzter Reindex",
      value: failedJobs ? "Jobs kritisch" : queuedJobs ? "Jobs laufen" : "Queue ruhig",
      detail: `${numberText(queuedJobs)} wartend / ${numberText(failedJobs)} fehlgeschlagen`,
      tone: failedJobs ? "is-error" : queuedJobs ? "is-stale" : "is-active"
    }
  ];
}

/**
 * Build health cards for the status panel.
 */
export function overviewHealthCards(state: AdminAiOverviewLoadState): AdminAiHealthCard[] {
  const readiness = recordField(state.summary, "readiness");
  const operationsJobs = recordField(state.operations, "background_jobs");
  const provider = stringField(state.aiStatus, "provider", "lokal");
  const model = stringField(state.aiStatus, "model", "lokal");
  const ready = state.aiStatus ? state.aiStatus.ready !== false : false;
  const queuedJobs = numberField(operationsJobs, "queue_length");
  const failedJobs = numberField(operationsJobs, "failed");

  return [
    {
      key: "ai",
      label: ready ? "bereit" : "checken",
      detail: `${provider} / ${model}`,
      tone: state.aiStatus ? (ready ? "is-active" : "is-error") : "is-muted"
    },
    {
      key: "rag",
      label: stringField(readiness, "status", "offen"),
      detail: stringField(readiness, "reasons", "Summary geladen"),
      tone: toneForStatus(readiness.status)
    },
    {
      key: "queue",
      label: failedJobs ? "kritisch" : queuedJobs ? "aktiv" : "ruhig",
      detail: `${numberText(queuedJobs)} wartend / ${numberText(failedJobs)} fehlgeschlagen`,
      tone: failedJobs ? "is-error" : queuedJobs ? "is-stale" : "is-active"
    }
  ];
}

/**
 * Build the model status card from `/api/v1/ai/status`.
 */
export function modelHealthCard(state: AdminAiOverviewLoadState): AdminAiHealthCard {
  const ready = state.aiStatus ? state.aiStatus.ready !== false : false;
  const model = stringField(state.aiStatus, "model", "lokal");
  return {
    key: "model",
    label: ready ? "bereit" : "Fallback / Kontrolle",
    detail: model,
    tone: state.aiStatus ? (ready ? "is-active" : "is-stale") : "is-muted"
  };
}

/**
 * Format a KPI value from Admin-AI summary payloads.
 */
export function kpiValue(summary: AdminAiPayload | null, key: string): string {
  const value = summary?.[key];
  if (key.includes("rate")) return percentText(value);
  if (key.includes("cost") || key.includes("usd")) return moneyText(value);
  if (key.includes("latency")) return `${numberText(value)} ms`;
  return numberText(value);
}

/**
 * Build business-facing metrics for the Admin Control Center overview.
 */
export function businessMetricRows(state: AdminAiOverviewLoadState): AdminAiStatRow[] {
  const retrievalQuality = recordField(state.summary, "retrieval_quality");
  const feedback = recordField(state.summary, "feedback");
  const readiness = recordField(state.summary, "readiness");

  return [
    { label: "Source health", value: stringField(readiness, "status", "offen") },
    { label: "Indexed/stale documents", value: stringField(readiness, "reasons", "keine Daten") },
    { label: "Antworten ohne Quellen", value: percentText(retrievalQuality.no_source_rate) },
    { label: "Low confidence answers", value: percentText(retrievalQuality.low_confidence_rate) },
    { label: "Negative feedback", value: numberText(feedback.negative || feedback.not_helpful || 0) },
    { label: "Tokens", value: numberText(state.summary?.total_tokens) },
    { label: "Costs", value: moneyText(state.summary?.estimated_cost_usd) },
    { label: "Usage", value: numberText(state.summary?.events_total) }
  ];
}

/**
 * Build the top admin action items from existing summary and operations data.
 */
export function adminActionItems(state: AdminAiOverviewLoadState): AdminAiActionItem[] {
  const summary = state.summary || {};
  const priceConfiguration = recordField(summary, "price_configuration");
  const retrievalQuality = recordField(summary, "retrieval_quality");
  const feedback = recordField(summary, "feedback");
  const operationsJobs = recordField(state.operations, "background_jobs");
  const actionItems: AdminAiActionItem[] = [];

  if (priceConfiguration.configured === false || stringField(priceConfiguration, "message").includes("nicht")) {
    actionItems.push({
      detail: stringField(priceConfiguration, "message", "Kostenkonfiguration prüfen."),
      key: "missing-cost-configuration",
      label: "Missing cost configuration",
      tone: "is-stale"
    });
  }

  if (numberField(summary, "error_rate") >= 0.1) {
    actionItems.push({
      detail: `${percentText(summary.error_rate)} Fehlerquote in der aktuellen Auswertung.`,
      key: "high-error-rate",
      label: "High error rate",
      tone: "is-error"
    });
  }

  if (numberField(retrievalQuality, "no_source_rate") >= 0.1) {
    actionItems.push({
      detail: `${percentText(retrievalQuality.no_source_rate)} Antworten ohne Quellen.`,
      key: "high-no-source-rate",
      label: "High answers without sources",
      tone: "is-stale"
    });
  }

  if (numberField(retrievalQuality, "knowledge_gaps_open") > 0) {
    actionItems.push({
      detail: `${numberText(retrievalQuality.knowledge_gaps_open)} offene Wissenslücken.`,
      key: "open-knowledge-gaps",
      label: "Open knowledge gaps",
      tone: "is-stale"
    });
  }

  if (numberField(retrievalQuality, "pending_approvals") > 0) {
    actionItems.push({
      detail: `${numberText(retrievalQuality.pending_approvals)} Freigaben warten.`,
      key: "pending-approvals",
      label: "Pending approvals",
      tone: "is-stale"
    });
  }

  if (numberField(operationsJobs, "failed") > 0 || numberField(operationsJobs, "running") > 0) {
    actionItems.push({
      detail: `${numberText(operationsJobs.running)} laufend / ${numberText(operationsJobs.failed)} fehlgeschlagen.`,
      key: "stuck-jobs",
      label: "Stuck or failed jobs",
      tone: numberField(operationsJobs, "failed") > 0 ? "is-error" : "is-stale"
    });
  }

  if (numberField(feedback, "negative") > 0 || numberField(feedback, "not_helpful") > 0) {
    actionItems.push({
      detail: `${numberText(feedback.negative || feedback.not_helpful)} negative Rückmeldungen.`,
      key: "negative-feedback",
      label: "Negative feedback",
      tone: "is-stale"
    });
  }

  return actionItems.length
    ? actionItems.slice(0, 6)
    : [
        {
          detail: "Keine offenen Action Items aus den vorhandenen Metriken.",
          key: "none",
          label: "No admin action required",
          tone: "is-active"
        }
      ];
}

/**
 * Build provider field cards from AI status payloads.
 */
export function providerFields(state: AdminAiOverviewLoadState): AdminAiProviderField[] {
  const ready = state.aiStatus ? state.aiStatus.ready !== false : false;
  return [
    {
      key: "provider",
      label: "Anbieter",
      value: stringField(state.aiStatus, "provider", "lokal"),
      detail: "Aktiver AI-Backend-Anbieter."
    },
    {
      key: "model",
      label: "Modell",
      value: stringField(state.aiStatus, "model", "lokal"),
      detail: "Modell für generative Antworten."
    },
    {
      key: "mode",
      label: "Betriebsmodus",
      value: ready ? "Modellbetrieb" : "Fallback / Kontrolle",
      detail: "Externes Modell oder lokaler Ausweichbetrieb."
    },
    {
      key: "streaming",
      label: "Streaming",
      value: state.aiStatus?.streaming_available ? "aktiv" : "nicht verfügbar",
      detail: state.aiStatus?.streaming_configured
        ? "Konfiguriert, API noch nicht freigegeben."
        : "Derzeit nicht konfiguriert."
    }
  ];
}

/**
 * Build provider diagnostic rows without exposing secrets.
 */
export function providerDetailRows(state: AdminAiOverviewLoadState): AdminAiStatRow[] {
  return [
    { label: "Provider", value: stringField(state.aiStatus, "provider", "lokal") },
    { label: "Modell", value: stringField(state.aiStatus, "model", "lokal") },
    {
      label: "Streaming",
      value: state.aiStatus?.streaming_available ? "aktiv" : "nicht verfügbar"
    },
    {
      label: "Letzter Fehler",
      value: stringField(state.aiStatus, "last_error", "kein letzter Fehler")
    }
  ];
}

/**
 * Build provider action rows that point operators to the stable backend contract.
 */
export function providerActionRows(state: AdminAiOverviewLoadState): AdminAiStatRow[] {
  const ready = state.aiStatus ? state.aiStatus.ready !== false : false;
  return [
    { label: "Aendern", value: ".env / Runtime-Konfiguration" },
    { label: "Endpoint", value: "/api/v1/ai/status" },
    { label: "Service", value: "app.ai.services.ai_status" },
    {
      label: "Admin-Hinweis",
      value: ready ? "Keine Aktion erforderlich" : "Key, Modell und Provider kontrollieren"
    }
  ];
}

/**
 * Convert a partial load failure into a stable Admin-AI overview state.
 */
export function failedOverviewState(error: unknown): Pick<AdminAiOverviewLoadState, "errorMessage"> {
  return {
    errorMessage: safeErrorMessage(error, "AI-Admin Overview konnte nicht komplett geladen werden.")
  };
}
