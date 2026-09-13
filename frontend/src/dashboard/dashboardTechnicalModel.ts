import { type DashboardPayload, type DashboardRuntimeData } from "./dashboardApi";
import { activeDashboardIncidents, assetText } from "./dashboardAssetModel";
import { taskIsOverdue, taskText } from "./dashboardTaskModel";

type DashboardSeverity = "critical" | "good" | "muted" | "warning";

export type DashboardSignalItem = {
  readonly detail: string;
  readonly href?: string;
  readonly label: string;
  readonly severity: DashboardSeverity;
  readonly value: string;
};

export type DashboardStatusRow = {
  readonly detail: string;
  readonly label: string;
  readonly severity: DashboardSeverity;
  readonly value: string;
};

type DashboardHeroStatus = {
  readonly className: string;
  readonly label: string;
  readonly meta: string;
  readonly updated: string;
};

/**
 * Return a nested object payload.
 */
function objectValue(payload: DashboardPayload | null | undefined, key: string): DashboardPayload {
  const value = payload?.[key];
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as DashboardPayload)
    : {};
}

/**
 * Return a numeric field from a payload.
 */
export function numberValue(payload: DashboardPayload | null | undefined, key: string): number {
  const value = payload?.[key];
  const parsed = typeof value === "number" ? value : Number(value || 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * Return the last retrieval SLO values from telemetry.
 */
export function retrievalSloValues(data: DashboardRuntimeData): DashboardPayload {
  return objectValue(objectValue(data.retrievalTelemetry, "retrieval_slo"), "last_values");
}

/**
 * Format a rate as percentage.
 */
function formatRatePercent(value: unknown): string {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

/**
 * Format a millisecond value.
 */
function formatMilliseconds(value: unknown): string {
  return `${Math.round(Number(value || 0))} ms`;
}

/**
 * Return the dashboard severity CSS class.
 */
export function dashboardSignalClass(severity: DashboardSeverity): string {
  if (severity === "critical") return "is-critical";
  if (severity === "warning") return "is-warning";
  if (severity === "good") return "is-good";
  return "is-muted";
}

/**
 * Return the status label for the worst active dashboard signal.
 */
function dashboardStatusLabel(signals: readonly DashboardSignalItem[]): string {
  if (signals.some((signal) => signal.severity === "critical")) return "Kritische Lage";
  if (signals.some((signal) => signal.severity === "warning")) return "Prüfen";
  if (signals.length) return "Stabil";
  return "Noch keine Daten";
}

/**
 * Return open knowledge gap count from the current dashboard data.
 */
function knowledgeGapCount(data: DashboardRuntimeData): number {
  return (
    data.knowledgeGaps.length ||
    numberValue(data.knowledgeStatus, "open_count") ||
    numberValue(data.knowledgeStatus, "open_gap_count")
  );
}

/**
 * Build the hero status text from React-owned dashboard data.
 */
export function dashboardHeroStatus(data: DashboardRuntimeData, isLoading: boolean, errorMessage: string): DashboardHeroStatus {
  if (isLoading) {
    return {
      className: "is-loading",
      label: "Daten werden geladen",
      meta: "Schicht- und Systemdaten werden geladen",
      updated: "Aktualisierung läuft"
    };
  }

  if (errorMessage) {
    return {
      className: "is-warning",
      label: "Teilweise geladen",
      meta: errorMessage,
      updated: new Date().toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })
    };
  }

  const signals = prioritySignals(data);
  return {
    className: dashboardSignalClass(signals[0]?.severity ?? "good"),
    label: dashboardStatusLabel(signals),
    meta: signals.length ? `${signals.length} aktive Hinweise` : "Keine kritischen Signale",
    updated: `Aktualisiert ${new Date().toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}`
  };
}

/**
 * Build priority signals for the AI operations rail.
 */
export function prioritySignals(data: DashboardRuntimeData): readonly DashboardSignalItem[] {
  const activeTasks = data.tasks.filter((task) => taskText(task, "status") !== "done" && taskText(task, "status") !== "cancelled");
  const criticalTasks = activeTasks.filter((task) => taskText(task, "priority") === "urgent" || taskIsOverdue(task));
  const operations = data.operationsSummary ?? {};
  const machines = objectValue(operations, "machines");
  const inventory = data.inventorySummary ?? objectValue(operations, "inventory");
  const sloValues = retrievalSloValues(data);
  const signals: DashboardSignalItem[] = [];

  if (criticalTasks.length) {
    signals.push({
      detail: taskText(criticalTasks[0], "title", "Sofort prüfen"),
      href: "/tasks",
      label: "Kritische Aufgaben",
      severity: "critical",
      value: String(criticalTasks.length)
    });
  }

  if (data.errors.length) {
    const incidents = activeDashboardIncidents(data.errors);
    signals.push({
      detail: assetText(incidents[0], "error_code", assetText(incidents[0], "title", "Fehlerliste")),
      href: "/errors",
      label: "Offene Störungen",
      severity: incidents.length > 2 ? "critical" : "warning",
      value: String(incidents.length)
    });
  }

  if (numberValue(machines, "repeat_faults")) {
    signals.push({
      detail: `${numberValue(machines, "faults")} Störungen im Zeitraum`,
      href: "/errors",
      label: "Wiederkehrende Probleme",
      severity: "warning",
      value: String(numberValue(machines, "repeat_faults"))
    });
  }

  if (numberValue(inventory, "critical_shortage_count")) {
    signals.push({
      detail: `${numberValue(inventory, "low_stock_count")} unter Mindestbestand`,
      href: "/inventory",
      label: "Materialengpässe",
      severity: "critical",
      value: String(numberValue(inventory, "critical_shortage_count"))
    });
  }

  if (numberValue(sloValues, "safety_risk_count")) {
    signals.push({
      detail: "KI-Sicherheit Events im Fenster",
      href: "/admin/ai",
      label: "Sicherheitsrisiken",
      severity: "critical",
      value: String(numberValue(sloValues, "safety_risk_count"))
    });
  }

  const gapCount = knowledgeGapCount(data);
  if (gapCount) {
    signals.push({
      detail: "offene Wissenslücken",
      href: "/admin/ai",
      label: "Wissenslücken",
      severity: gapCount > 3 ? "critical" : "warning",
      value: String(gapCount)
    });
  }

  const lowConfidenceRate = numberValue(sloValues, "low_confidence_rate");
  const noSourceRate = numberValue(sloValues, "no_source_rate");
  if (lowConfidenceRate >= 0.15 || noSourceRate >= 0.1) {
    signals.push({
      detail: "Niedrige Sicherheit oder fehlende Quellen",
      href: "/admin/ai",
      label: "Suchqualität",
      severity: lowConfidenceRate >= 0.25 || noSourceRate >= 0.2 ? "critical" : "warning",
      value: formatRatePercent(Math.max(lowConfidenceRate, noSourceRate))
    });
  }

  if (numberValue(sloValues, "stale_index_count")) {
    signals.push({
      detail: "Dokumente sollten reindexiert werden",
      href: "/admin/ai",
      label: "Veralteter Index",
      severity: "warning",
      value: String(numberValue(sloValues, "stale_index_count"))
    });
  }

  const severityRank: Record<DashboardSeverity, number> = { critical: 0, warning: 1, good: 2, muted: 3 };
  return signals.sort((first, second) => severityRank[first.severity] - severityRank[second.severity]).slice(0, 7);
}

/**
 * Build warning feed items from dashboard and AI signals.
 */
export function warningSignals(data: DashboardRuntimeData): readonly DashboardSignalItem[] {
  return prioritySignals(data).filter((signal) => signal.severity === "critical" || signal.severity === "warning").slice(0, 6);
}

/**
 * Build AI system rows.
 */
export function aiSystemRows(data: DashboardRuntimeData): readonly DashboardStatusRow[] {
  const aiStatus = data.aiStatus ?? {};
  const sloValues = retrievalSloValues(data);
  const ready = aiStatus.ready === true;

  return [
    {
      detail: ready ? "bereit" : "prüfen",
      label: "KI-Anbieter",
      severity: ready ? "good" : "warning",
      value: assetText(aiStatus, "provider", "-")
    },
    {
      detail: aiStatus.streaming_available
        ? "Streaming aktiv"
        : aiStatus.streaming_configured
          ? "Konfiguriert, API noch nicht freigegeben"
          : "Streaming aus",
      label: "Modell",
      severity: "muted",
      value: assetText(aiStatus, "model", "-")
    },
    {
      detail: "Antwortkontext",
      label: "Suchzeit P95",
      severity: numberValue(sloValues, "retrieval_p95_ms") > 2500 ? "warning" : "good",
      value: formatMilliseconds(sloValues.retrieval_p95_ms)
    },
    {
      detail: "KI-Anbieter oder Suche",
      label: "Ausweichantworten",
      severity: numberValue(sloValues, "fallback_rate") >= 0.1 ? "warning" : "good",
      value: formatRatePercent(sloValues.fallback_rate)
    },
    {
      detail: "Index-Synchronisation",
      label: "Index-Sync-Fehler",
      severity: numberValue(sloValues, "vector_sync_failure_count") ? "critical" : "good",
      value: String(numberValue(sloValues, "vector_sync_failure_count"))
    }
  ];
}

/**
 * Build risk radar rows.
 */
export function riskRows(data: DashboardRuntimeData): readonly DashboardStatusRow[] {
  const sloValues = retrievalSloValues(data);
  return [
    {
      detail: "Sicherheitsereignisse",
      label: "Sicherheit",
      severity: numberValue(sloValues, "safety_risk_count") ? "critical" : "good",
      value: String(numberValue(sloValues, "safety_risk_count"))
    },
    {
      detail: "Antworten unter Schwelle",
      label: "Niedrige Sicherheit",
      severity: numberValue(sloValues, "low_confidence_rate") >= 0.15 ? "warning" : "good",
      value: formatRatePercent(sloValues.low_confidence_rate)
    },
    {
      detail: "Antworten ohne Quelle",
      label: "Ohne Quellen",
      severity: numberValue(sloValues, "no_source_rate") >= 0.1 ? "warning" : "good",
      value: formatRatePercent(sloValues.no_source_rate)
    },
    {
      detail: "KI-Anbieter oder Suche",
      label: "Ausweichantworten",
      severity: numberValue(sloValues, "fallback_rate") >= 0.1 ? "warning" : "good",
      value: formatRatePercent(sloValues.fallback_rate)
    },
    {
      detail: "Nutzerrückmeldungen",
      label: "Negatives Feedback",
      severity: numberValue(sloValues, "negative_feedback_rate") >= 0.1 ? "warning" : "good",
      value: formatRatePercent(sloValues.negative_feedback_rate)
    },
    {
      detail: "gefilterte Kandidaten",
      label: "Berechtigungsfilter",
      severity: "muted",
      value: String(numberValue(sloValues, "permission_filtered_candidate_count"))
    }
  ];
}

/**
 * Build knowledge health rows.
 */
export function knowledgeRows(data: DashboardRuntimeData): readonly DashboardStatusRow[] {
  const status = data.knowledgeStatus ?? {};
  const vectorStatus = objectValue(status, "vector_store");
  const indexed = numberValue(status, "indexed");
  const documents = numberValue(status, "documents");
  const chunks = numberValue(status, "chunks");
  const stale = numberValue(status, "stale");
  const missingChunks = numberValue(vectorStatus, "missing_chunk_count");
  const reindexNeeded = vectorStatus.reindex_recommended === true;
  const reasons = Array.isArray(vectorStatus.reindex_reasons) ? vectorStatus.reindex_reasons.join(", ") : "";
  const gapCount = knowledgeGapCount(data);

  return [
    {
      detail: `${chunks} Textabschnitte`,
      label: "Dokumente indexiert",
      severity: documents && indexed < documents ? "warning" : "good",
      value: `${indexed}/${documents}`
    },
    {
      detail: "Aging und Reindex",
      label: "Veraltete Dokumente",
      severity: stale ? "warning" : "good",
      value: String(stale)
    },
    {
      detail: "DB zu Vektor Store",
      label: "Fehlende Textabschnitte",
      severity: missingChunks ? "critical" : "good",
      value: String(missingChunks)
    },
    {
      detail: reasons,
      label: "Reindex",
      severity: reindexNeeded ? "warning" : "good",
      value: reindexNeeded ? "empfohlen" : "nicht nötig"
    },
    {
      detail: "offene Lücken",
      label: "Wissenslücken",
      severity: gapCount ? "warning" : "good",
      value: String(gapCount)
    }
  ];
}

/**
 * Build technical index rows.
 */
export function technicalIndexRows(data: DashboardRuntimeData): readonly DashboardStatusRow[] {
  const status = data.knowledgeStatus ?? {};
  const sloValues = retrievalSloValues(data);
  const vectorStatus = objectValue(status, "vector_store");
  const reindexNeeded = vectorStatus.reindex_recommended === true;
  const indexed = numberValue(status, "indexed");
  const documents = numberValue(status, "documents");
  const chunks = numberValue(status, "chunks");

  return [
    {
      detail: `${indexed}/${documents} Dokumente, ${chunks} Textabschnitte`,
      label: "Dokument-/Index-Status",
      severity: reindexNeeded ? "warning" : "good",
      value: reindexNeeded ? "Reindex" : "OK"
    },
    {
      detail: "Offene Lücken",
      label: "Wissenslücken",
      severity: knowledgeGapCount(data) ? "warning" : "good",
      value: String(knowledgeGapCount(data))
    },
    {
      detail: `${formatRatePercent(sloValues.no_source_rate)} ohne Quellen`,
      label: "Suchzeit P95",
      severity: numberValue(sloValues, "retrieval_p95_ms") > 2500 ? "warning" : "good",
      value: formatMilliseconds(sloValues.retrieval_p95_ms)
    },
    {
      detail: "Antwortqualität",
      label: "Niedrige Sicherheit",
      severity: numberValue(sloValues, "low_confidence_rate") >= 0.15 ? "warning" : "good",
      value: formatRatePercent(sloValues.low_confidence_rate)
    }
  ];
}
