import { type ReactNode } from "react";
import {
  type AdminAiTechnicalProps,
  monitoringValue,
  objectPayload,
  technicalItems
} from "../adminAiTechnicalModel";
import { ragText } from "../adminAiRagBoardModel";
import { AdminAiObservabilityLangfuse } from "./AdminAiObservabilityLangfuse";
import { isPayload } from "./AdminAiShared";
import { ObservabilityLogsPanel } from "./AdminAiTechnicalLogs";
import { RetrievalSection } from "./AdminAiTechnicalRetrieval";
import { DiagnosticsExpertSection } from "./AdminAiTechnicalDiagnostics";
import { IndexingSection } from "./AdminAiTechnicalIndexing";

const OBSERVABILITY_ESSENTIAL_KPIS = [
  ["total_requests", "Anfragen", "0"],
  ["failed_requests", "Fehler", "0"],
  ["average_response_ms", "Antwortzeit", "0 ms"],
  ["no_source_answers", "Ohne Quellen", "0"],
  ["governance_alert_count", "Alerts", "0"],
  ["retrieval_hit_rate", "Trefferquote", "0%"]
] as const;

/**
 * Render the technical Admin-AI diagnostics areas.
 */
export function AdminAiTechnical(props: AdminAiTechnicalProps): ReactNode {
  const { onRefresh, technicalState } = props;
  const observability = technicalState.observability || {};
  const metrics = objectPayload(observability.metrics);
  const quality = objectPayload(observability.quality_metrics);
  const logs = Array.isArray(observability.logs) ? observability.logs.filter(isPayload) : technicalItems(observability);
  const runtime = objectPayload(technicalState.aiStatus?.langfuse);
  const traceHost = ragText(runtime.host, "https://cloud.langfuse.com");

  return (
    <section className="ai-admin-area ai-observability-hub" id="ai-technical">
      <div className="ai-admin-area-header">
        <div>
          <span className="section-kicker">Observability</span>
          <h3>Logging, Tracing und Metriken</h3>
          <p className="panel-meta">
            Langfuse, die wichtigsten Kennzahlen und Protokolle im Blick. Detaildiagnose im Expertenmodus.
          </p>
        </div>
        <div className="toolbar">
          <span className="badge badge-ai">
            {technicalState.isLoading ? "lädt" : "bereit"}
          </span>
          <button className="btn btn-secondary btn-sm" type="button" onClick={onRefresh}>
            Aktualisieren
          </button>
        </div>
      </div>
      <AdminAiObservabilityLangfuse aiStatus={technicalState.aiStatus} summary={technicalState.summary} />
      <section className="panel ai-observability-essentials">
        <div className="panel-header">
          <div>
            <h3>Kern-Kennzahlen (30 Tage)</h3>
            <p className="panel-meta">Schneller Überblick vor den Protokollen.</p>
          </div>
        </div>
        <div className="dashboard-grid dashboard-grid-3">
          {OBSERVABILITY_ESSENTIAL_KPIS.map(([key, label, fallback]) => (
            <article className="metric-card" key={key}>
              <span>{label}</span>
              <strong>
                {metrics[key] == null && quality[key] == null
                  ? fallback
                  : monitoringValue(key, metrics[key] ?? quality[key])}
              </strong>
            </article>
          ))}
        </div>
      </section>
      <ObservabilityLogsPanel isLoading={technicalState.isLoading} logs={logs} traceHost={traceHost} />
      <details className="help-disclosure ui-secondary-panel admin-ai-expert-mode" id="ai-observability-expert">
        <summary>
          <span className="admin-ai-technical-disclosure-copy">
            <strong>Expertenmodus</strong>
            <small>Metrik-Cockpit, Retrieval-Debug, Golden Eval, Jobs und Reindex.</small>
          </span>
        </summary>
        <div className="help-disclosure-body admin-ai-technical-disclosure-body">
          <nav className="admin-technical-nav" aria-label="Observability Bereiche">
            <a className="action-hint-item is-muted" href="#ai-diagnostics">
              <div className="action-hint-copy">
                <strong>Metriken & Alerts</strong>
                <small>Governance, Workflows, Wissenslücken.</small>
              </div>
              <span>Details</span>
            </a>
            <a className="action-hint-item is-muted" href="#ai-retrieval">
              <div className="action-hint-copy">
                <strong>Tracing / Retrieval</strong>
                <small>Quellenabruf-Ablauf, SLO und Golden Eval.</small>
              </div>
              <span>Tracing</span>
            </a>
            <a className="action-hint-item is-muted" href="#ai-indexing-status">
              <div className="action-hint-copy">
                <strong>Jobs & Index</strong>
                <small>Reindex, Queue und Background-Jobs.</small>
              </div>
              <span>Jobs</span>
            </a>
          </nav>
          <DiagnosticsExpertSection {...props} />
          <RetrievalSection {...props} />
          <IndexingSection {...props} />
        </div>
      </details>
    </section>
  );
}
