import { type ReactNode } from "react";

import {
  langfuseMetricValue,
  langfuseStatus,
  type AdminAiEffectivenessState
} from "./adminAiEffectivenessModel";
import { type AdminAiPayload } from "./adminAiApi";
import { ragText } from "./adminAiRagBoardModel";
import { objectPayload } from "./adminAiTechnicalModel";

const LANGFUSE_KPIS = [
  ["total_cost_usd", "Kosten (30 Tage)"],
  ["total_tokens", "Tokens"],
  ["observation_count", "Observations"],
  ["cost_per_1k_tokens", "Kosten / 1k Tokens"]
] as const;

type AdminAiObservabilityLangfuseProps = {
  readonly aiStatus: AdminAiPayload | null;
  readonly summary: AdminAiPayload | null;
};

/**
 * Build a minimal effectiveness state for shared Langfuse metric helpers.
 */
function langfuseMetricState(summary: AdminAiPayload | null): AdminAiEffectivenessState {
  return {
    summary,
    telemetry: null,
    userCosts: [],
    errorMessage: "",
    isLoading: false
  };
}

/**
 * Return a safe Langfuse UI URL for a trace id.
 */
function langfuseTraceUrl(host: string, traceId: string): string {
  const base = host.replace(/\/$/, "");
  if (!base || !traceId) return "";
  return `${base}/trace/${encodeURIComponent(traceId)}`;
}

/**
 * Render Langfuse tracing status and compact cost metrics on Observability.
 */
export function AdminAiObservabilityLangfuse({
  aiStatus,
  summary
}: AdminAiObservabilityLangfuseProps): ReactNode {
  const runtime = objectPayload(aiStatus?.langfuse);
  const metricState = langfuseMetricState(summary);
  const langfuse = langfuseStatus(metricState);
  const host = ragText(runtime.host, ragText(summary?.langfuse_host, "https://cloud.langfuse.com"));
  const ready = Boolean(runtime.ready);
  const configured = Boolean(runtime.configured);
  const enabled = Boolean(runtime.enabled);

  return (
    <section className="panel ai-observability-langfuse" data-ai-langfuse-panel>
      <div className="panel-header">
        <div>
          <h3>Langfuse Tracing</h3>
          <p className="panel-meta">
            Externe Traces und Kostenmetriken. Vollständige Kostenansicht unter Betrieb oder
            /admin/ai/effectiveness.
          </p>
        </div>
        <span className={`badge badge-ai ${langfuse.tone}`} data-langfuse-metrics-status>
          {ready ? "Tracing aktiv" : langfuse.label}
        </span>
      </div>
      <div className="ai-observability-langfuse-status">
        <article className="metric-card">
          <span>Integration</span>
          <strong data-langfuse-runtime-ready>{ready ? "bereit" : enabled ? "konfiguration prüfen" : "deaktiviert"}</strong>
        </article>
        <article className="metric-card">
          <span>Host</span>
          <strong data-langfuse-runtime-host>
            {host ? (
              <a href={host} rel="noreferrer" target="_blank">
                Langfuse öffnen
              </a>
            ) : (
              "-"
            )}
          </strong>
        </article>
        <article className="metric-card">
          <span>Schlüssel</span>
          <strong data-langfuse-runtime-configured>{configured ? "gesetzt" : "fehlt"}</strong>
        </article>
      </div>
      <div className="dashboard-grid dashboard-grid-4 mt-4">
        {LANGFUSE_KPIS.map(([key, label]) => (
          <article className="metric-card" key={key}>
            <span>{label}</span>
            <strong data-langfuse-metric={key}>{langfuseMetricValue(metricState, key)}</strong>
          </article>
        ))}
      </div>
      {!ready ? (
        <p className="panel-meta mt-4" data-langfuse-setup-hint>
          LANGFUSE_ENABLED, LANGFUSE_PUBLIC_KEY und LANGFUSE_SECRET_KEY in .env setzen. Protokolle
          unten zeigen Trace-IDs sobald Anfragen laufen.
        </p>
      ) : null}
    </section>
  );
}

/**
 * Render a Langfuse trace link for one observability log row.
 */
export function ObservabilityLangfuseTraceLink({
  host,
  traceId
}: {
  readonly host: string;
  readonly traceId: string;
}): ReactNode {
  const url = langfuseTraceUrl(host, traceId);
  if (!url) return <span>-</span>;
  return (
    <a href={url} rel="noreferrer" target="_blank" data-langfuse-trace-link>
      Trace
    </a>
  );
}
