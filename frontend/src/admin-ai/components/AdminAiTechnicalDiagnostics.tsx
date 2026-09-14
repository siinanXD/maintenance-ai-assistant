import { type ReactNode } from "react";
import {
  type AdminAiTechnicalProps,
  metricLabel,
  monitoringValue,
  objectPayload,
  technicalDateTime,
  technicalItems,
  technicalReference
} from "../adminAiTechnicalModel";
import { ragText } from "../adminAiRagBoardModel";
import {
  CollapsibleMetricGrid,
  DataTable,
  debugRequests,
  isPayload,
  StatRow,
  StatsList,
  topList
} from "./AdminAiShared";
import { numberText, percentText } from "../adminAiFormat";

const MONITORING_KPIS = [
  ["total_requests", "Requests", "0"],
  ["successful_requests", "Erfolgreich", "0"],
  ["failed_requests", "Fehlgeschlagen", "0"],
  ["average_response_ms", "Antwortzeit Ø", "0 ms"],
  ["average_retrieval_ms", "Quellenabruf Ø", "0 ms"],
  ["total_tokens", "Tokenverbrauch", "0"],
  ["request_success_rate", "Erfolgsquote", "0%"],
  ["structured_answer_count", "Strukturierte Antworten", "0"],
  ["rag_answer_count", "RAG-Antworten", "0"],
  ["no_source_answers", "Ohne Quellen", "0"],
  ["low_confidence_answers", "Niedrige Sicherheit", "0"],
  ["governance_alert_count", "Governance Alerts", "0"],
  ["governance_critical_alert_count", "Kritische Alerts", "0"],
  ["atlas_queries", "Atlas Queries", "0"],
  ["atlas_errors", "Atlas Fehler", "0"],
  ["atlas_latency", "Atlas Latenz Ø", "0 ms"],
  ["atlas_fallbacks", "Atlas Fallbacks", "0"],
  ["atlas_sync_failures", "Atlas Sync-Fehler", "0"],
  ["atlas_vector_count", "Atlas Vektoren", "0"],
  ["atlas_reindex_required", "Atlas Reindex", "nein"],
  ["source_count_average", "Quellen Ø", "0"],
  ["empty_retrieval_rate", "Leere Abrufe", "0%"],
  ["hallucination_warning_count", "Halluzinationswarnungen", "0"],
  ["retrieval_hit_rate", "Trefferquote", "0%"],
  ["average_similarity_score", "Similarity Ø", "0%"]
] as const;

/**
 * Render extended observability panels for expert diagnostics.
 */
export function DiagnosticsExpertSection({ technicalState }: AdminAiTechnicalProps): ReactNode {
  const observability = technicalState.observability || {};
  const metrics = objectPayload(observability.metrics);
  const quality = objectPayload(observability.quality_metrics);
  const governance = objectPayload(observability.governance);
  const governanceAlerts = Array.isArray(observability.alerts)
    ? observability.alerts.filter(isPayload)
    : Array.isArray(governance.alerts)
      ? governance.alerts.filter(isPayload)
      : [];
  const retrieval = objectPayload(observability.retrieval_monitoring);
  const debugTools = objectPayload(observability.debug_tools);
  const logs = Array.isArray(observability.logs) ? observability.logs.filter(isPayload) : technicalItems(observability);
  const workflows = Array.isArray(observability.workflows) ? observability.workflows.filter(isPayload) : [];
  const topErrors = Array.isArray(observability.top_errors) ? observability.top_errors.filter(isPayload) : [];
  const gaps = Array.isArray(observability.knowledge_gaps) ? observability.knowledge_gaps.filter(isPayload) : [];
  const topQuestions = observability.top_questions || metrics.top_questions || metrics.frequent_questions;
  const sourceDistribution = observability.source_distribution || metrics.source_distribution_rows;
  const structuredModules = Array.isArray(metrics.top_structured_modules)
    ? metrics.top_structured_modules.filter(isPayload)
    : [];
  const structuredDomainRows = Array.isArray(metrics.structured_domain_distribution_rows)
    ? metrics.structured_domain_distribution_rows.filter(isPayload)
    : structuredModules;
  const frequentSearchTerms = Array.isArray(metrics.frequent_search_terms)
    ? metrics.frequent_search_terms.filter(isPayload)
    : [];
  const noSourceRows = [
    ["Fehlende Berechtigung", metrics.no_source_permission_denied_count || 0],
    ["Keine Daten gefunden", metrics.no_source_no_data_count || 0],
    ["Beantwortet ohne Quellen", metrics.no_source_answer_count || 0],
    ["Quellen je beantworteter Frage", monitoringValue("source_count_average_answered", metrics.source_count_average_answered)]
  ] as const;

  return (
    <section className="ai-admin-area ai-observability-expert-metrics">
      <details className="help-disclosure ui-secondary-panel">
        <summary>Letzte fehlgeschlagene Abfragen ({Math.min(logs.length, 5)})</summary>
        <div className="help-disclosure-body">
          <p className="panel-meta">Aus Audit-Ereignissen; ohne Rohfrage oder Antworttext.</p>
          <div className="ai-failed-query-list">
            {logs.slice(0, 5).map((item) => (
              <StatRow key={ragText(item.id)} label={technicalReference("Audit", item.id)} value={ragText(item.status || item.error_category, "ok")} />
            ))}
          </div>
        </div>
      </details>
      <details className="help-disclosure ui-secondary-panel">
        <summary>Metrik-Cockpit und Governance</summary>
        <div className="help-disclosure-body ai-observability-panel">
        <CollapsibleMetricGrid
          previewCount={4}
          summaryLabel="Weitere Monitoring-Metriken"
          cards={MONITORING_KPIS.map(([key, label, fallback]) => (
            <article className="metric-card" key={key}>
              <span>{label}</span>
              <strong>
                {metrics[key] == null && quality[key] == null ? fallback : monitoringValue(key, metrics[key] ?? quality[key])}
              </strong>
            </article>
          ))}
        />
        <div className="content-grid two-columns mt-4"><StatsList rows={topList(topQuestions)} empty={["Fragen", "keine Daten"]} /><StatsList rows={topList(sourceDistribution)} empty={["Quellen", "keine Daten"]} /></div>
        <div className="content-grid two-columns mt-4"><StatsList rows={structuredDomainRows.map((item) => [item.label || item.module, item.count] as const)} empty={["Strukturierte Bereiche", "keine Daten"]} /><StatsList rows={frequentSearchTerms.map((item) => [item.term, item.count] as const)} empty={["Suchbegriffe", "keine Daten"]} /></div>
        <div className="content-grid two-columns mt-4"><StatsList rows={noSourceRows} empty={["Antworten ohne Quellen", "keine Daten"]} /><StatsList rows={[["Alle Antworten", monitoringValue("source_count_average", metrics.source_count_average)], ["Beantwortete Fragen", monitoringValue("source_count_average_answered", metrics.source_count_average_answered)]]} empty={["Quellen", "keine Daten"]} /></div>
      <section className="panel">
        <div className="panel-header">
          <div><h3>AI Governance Alerts</h3><p className="panel-meta">Konfigurierbare Warnungen aus Observability, Retrieval-Qualität, Kosten, Tokens und Vector-Store-Status.</p></div>
          <span className="badge badge-ai">{ragText(governance.status, "ok")}</span>
        </div>
        <DataTable caption="Aktive AI-Governance-Alerts" headers={["Schwere", "Regel", "Metrik", "Wert", "Schwelle", "Aktion"]} rows={governanceAlerts.map((alert) => [
          alert.severity,
          alert.title || alert.rule,
          metricLabel(ragText(alert.metric)),
          monitoringValue(ragText(alert.metric), alert.value),
          monitoringValue(ragText(alert.metric), alert.threshold),
          alert.recommended_action
        ])} />
      </section>
      <section className="panel"><div className="panel-header"><h3>Quellenabruf Monitoring</h3><span className="panel-meta">Top Treffer, schlechte Treffer, Textabschnitt-Nutzung und Dokumentverteilung.</span></div><div className="content-grid two-columns"><StatsList rows={topList(retrieval.top_hits)} empty={["Treffer", "keine Daten"]} /><StatsList rows={topList(retrieval.poor_hits)} empty={["Schlechte Treffer", "keine Daten"]} /></div><div className="content-grid two-columns mt-4"><StatsList rows={topList(retrieval.chunk_usage)} empty={["Textabschnitte", "keine Daten"]} /><StatsList rows={Object.entries(quality).slice(0, 6).map(([key, value]) => [metricLabel(key), monitoringValue(key, value)] as const)} empty={["Qualität", "keine Daten"]} /></div></section>
      <section className="panel"><div className="panel-header"><h3>Workflow-Kosten und Fehler</h3><span className="panel-meta">Metadata-only Auswertung ohne Prompt- oder Antworttexte</span></div><div className="content-grid two-columns"><DataTable caption="AI-Workflows nach Ereignissen, Fehlern, Ausweichbetrieb, Tokens und Kosten" headers={["Workflow", "Ereignisse", "Ausweichbetrieb", "Fehler", "Tokens", "Kosten", "Latenz"]} rows={workflows.map((item) => [item.workflow, item.events, percentText(item.fallback_rate || 0), item.errors, item.total_tokens, item.estimated_cost_usd, `${numberText(item.average_latency_ms || 0)} ms`])} /><StatsList rows={topErrors.map((item) => [item.error_category, item.count] as const)} empty={["AI Fehler", "keine Fehler im Zeitraum"]} /></div></section>
      <section className="panel"><div className="panel-header"><h3>Wissenslücken</h3><span className="panel-meta">{numberText(gaps.length)} offen</span></div><DataTable caption="Offene Wissenslücken aus KI-Fragen ohne belastbare Quellen" headers={["Referenz", "Bereich", "Maschine", "Status", "Treffer", "Zuletzt"]} rows={gaps.map((gap) => [technicalReference("Gap", gap.id), gap.department, gap.machine, gap.status, gap.occurrence_count, technicalDateTime(gap.last_seen_at)])} /></section>
      <section className="panel"><div className="panel-header"><h3>Debug Tools</h3><div className="toolbar"><select className="input input-bordered" aria-label="AI-Anfrage analysieren">{debugRequests(debugTools).map((item) => <option key={ragText(item.id)} value={ragText(item.id)}>{technicalReference("Chat", item.id)}</option>)}</select></div></div><div className="content-grid two-columns"><div className="ai-monitor-list"><StatRow label="Quellen" value={objectPayload(debugTools.request_analysis).source_count || 0} /></div><pre className="ai-debug-prompt">{ragText(objectPayload(debugTools.prompt_blueprint).system_prompt, "Kein Prompt-Blueprint geladen.")}</pre></div></section>
        </div>
      </details>
    </section>
  );
}
