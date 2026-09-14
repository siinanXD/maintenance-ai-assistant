import { type ReactNode } from "react";
import {
  type AdminAiTechnicalProps,
  flowStatusLabel,
  metricLabel,
  objectPayload,
  retrievalSloValue,
  retrievalSloValues,
  selectedRetrievalDebugItem,
  technicalDateTime,
  technicalReference
} from "../adminAiTechnicalModel";
import { ragText } from "../adminAiRagBoardModel";
import {
  CollapsibleMetricGrid,
  DataTable,
  debugSteps,
  filterChange,
  isPayload,
  StatRow,
  StatsList
} from "./AdminAiShared";
import { numberText, percentText } from "../adminAiFormat";

const RETRIEVAL_SLO_KPIS = [
  ["retrieval_p95_ms", "P95 Suchzeit", "0 ms"],
  ["no_source_rate", "Antworten ohne Quellen", "0%"],
  ["low_confidence_rate", "Niedrige Sicherheit", "0%"],
  ["permission_filtered_candidate_count", "Berechtigungsfilter", "0"],
  ["negative_feedback_rate", "Negatives Feedback", "0%"],
  ["safety_risk_count", "Sicherheitsrisiken", "0"],
  ["fallback_rate", "Ausweichantworten", "0%"],
  ["index_sync_risks", "Index/Sync Risiken", "0"]
] as const;

/**
 * Render retrieval debug, SLO and golden-eval panels.
 */
export function RetrievalSection({
  onFilterChange,
  onRefresh,
  onRunEvaluation,
  technicalState
}: AdminAiTechnicalProps): ReactNode {
  const sloValues = retrievalSloValues(technicalState.telemetry);
  const slo = objectPayload(technicalState.telemetry?.retrieval_slo);
  const trends = objectPayload(slo.trends);
  const warnings = Array.isArray(slo.warnings) ? slo.warnings.filter(isPayload) : [];
  const evaluationHistory = objectPayload(technicalState.telemetry?.retrieval_evaluation_history);
  const latestEvaluation = objectPayload(evaluationHistory.latest);
  const evaluationRuns = Array.isArray(evaluationHistory.runs) ? evaluationHistory.runs.filter(isPayload) : [];
  const regressionSignals = Array.isArray(evaluationHistory.regression_signals)
    ? evaluationHistory.regression_signals.filter(isPayload)
    : [];
  const selectedDebug = selectedRetrievalDebugItem(technicalState.retrievalDebug);

  return (
    <section className="ai-admin-area" id="ai-retrieval">
      <div className="ai-admin-area-header">
        <div>
          <span className="section-kicker">2. Quellenabruf</span>
          <h3>Warum wurden Quellen gefunden, gefiltert oder verworfen?</h3>
          <p className="panel-meta">Prompt-sichere Analyse für Abfrage-Klassifizierung, SQL-Ausweichbetrieb, Keyword-Suche, Vektorsuche, Bewertungen und finale Quellen.</p>
        </div>
        <span className="badge badge-ai">Quellenabruf geladen</span>
      </div>
      <section className="panel">
        <div className="panel-header">
          <div><h3>Suchqualität SLO</h3><p className="panel-meta">Qualitäts- und Betriebsmetriken für AI-Antworten.</p></div>
          <span className="badge badge-ai">{ragText(slo.status, "Noch nicht geladen")}</span>
        </div>
        <CollapsibleMetricGrid
          summaryLabel="Weitere SLO-Metriken"
          cards={RETRIEVAL_SLO_KPIS.map(([key, label, fallback]) => (
            <article className="metric-card" key={key}>
              <span>{label}</span>
              <strong>{sloValues[key] == null ? fallback : retrievalSloValue(key, sloValues[key])}</strong>
            </article>
          ))}
        />
        <div className="content-grid two-columns mt-4">
          <StatsList rows={Object.entries(trends).map(([key, value]) => [metricLabel(key), retrievalSloValue(key, objectPayload(value).current)] as const)} empty={["Trends", "noch keine SLO-Trends"]} />
          <StatsList rows={warnings.map((warning) => [metricLabel(ragText(warning.metric)), `${ragText(warning.status)} ab ${retrievalSloValue(ragText(warning.metric), warning.threshold)}`] as const)} empty={["Warnungen", "keine aktiven SLO-Warnungen"]} />
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div><h3>Quellenabruf Analyse</h3><p className="panel-meta">Nur-Lese Nachvollziehbarkeit ohne Roh-Prompts, Antworten oder Textabschnitt-Volltexte.</p></div>
          <div className="toolbar admin-ai-toolbar">
            <input className="input input-bordered" placeholder="Quellenabruf-Fälle filtern" value={technicalState.filters.debugQuery} onChange={filterChange(onFilterChange, "debugQuery")} />
            <select className="input input-bordered" aria-label="Nach Abfrage-Typ filtern" value={technicalState.filters.debugType} onChange={filterChange(onFilterChange, "debugType")}>
              <option value="">Alle Abfrage-Typen</option>
              <option value="error_analysis">Fehleranalyse</option>
              <option value="machine_question">Maschinenfrage</option>
              <option value="inventory_question">Inventarfrage</option>
              <option value="task_question">Aufgabefrage</option>
              <option value="document_question">Dokumentfrage</option>
              <option value="safety_question">Sicherheitsfrage</option>
              <option value="knowledge_gap">Wissenslücke</option>
              <option value="trend_history_question">Trend/Historie</option>
              <option value="general_question">Allgemein</option>
            </select>
            <button className="btn btn-secondary" type="button" onClick={onRefresh}>Aktualisieren</button>
          </div>
        </div>
        <div className="ai-retrieval-inspector">
          <div className="ai-retrieval-metrics">
            <StatRow label="Quellen" value={selectedDebug?.source_count || 0} />
            <StatRow label="Gefiltert" value={selectedDebug?.filtered_candidate_count || 0} />
            <StatRow label="Dauer" value={`${numberText(selectedDebug?.retrieval_duration_ms || 0)} ms`} />
          </div>
          <section className="retrieval-flow-panel" aria-label="AI Quellenabruf Ablauf">
            <div className="retrieval-flow-header">
              <div><span className="section-kicker">Warum diese Antwort?</span><h4>AI Quellenabruf Ablauf</h4><p className="panel-meta">Prompt-sichere Timeline vom Abfrage-Verständnis bis zur finalen Antwort.</p></div>
              <div className="retrieval-flow-header-actions"><span className="badge badge-ai">{selectedDebug ? "geladen" : "Noch nicht geladen"}</span><span className="panel-meta">{selectedDebug ? `${numberText(selectedDebug.retrieval_duration_ms || 0)} ms` : "-"}</span></div>
            </div>
            <div className="retrieval-flow-summary">{selectedDebug ? technicalReference("Chat", selectedDebug.chat_message_id || selectedDebug.id) : "Kein Debug-Datensatz ausgewählt."}</div>
            <div className="retrieval-flow-timeline">
              {debugSteps(selectedDebug).map((step, index) => <StatRow key={index} label={ragText(step.step || step.label, `Schritt ${index + 1}`)} value={flowStatusLabel(step.status)} />)}
            </div>
            <div className="content-grid two-columns mt-4">
              <div className="retrieval-flow-source-map"><StatRow label="Finale Quellen" value={selectedDebug?.final_visible_sources || selectedDebug?.source_count || 0} /></div>
              <div className="retrieval-flow-answer"><StatRow label="Antwort" value={ragText(selectedDebug?.answer_preview, "metadata-only")} /></div>
            </div>
          </section>
        </div>
        <DataTable caption="Prompt-sichere Quellenabruf-Debug-Daten mit Abfrage-Typ, Quellen, Sicherheit und Konflikten" headers={["Zeit", "Referenz", "Typ", "Quellen", "Sicherheit", "Konflikte", "Dauer", "Ablauf"]} rows={technicalState.retrievalDebug.map((item) => [
          technicalDateTime(item.created_at),
          technicalReference("Chat", item.chat_message_id || item.id),
          item.query_type,
          item.source_count || item.final_visible_sources || 0,
          item.confidence_level || item.confidence_score || "-",
          item.conflict_count || 0,
          `${numberText(item.retrieval_duration_ms || 0)} ms`,
          "anzeigen"
        ])} />
      </section>

      <section className="panel">
        <div className="panel-header">
          <div><h3>Golden Eval Historie</h3><p className="panel-meta">Regressionen und Qualitätstrends für bekannte Quellenabruf-Fragen.</p></div>
          <div className="toolbar"><span className="badge badge-ai">{evaluationRuns.length ? "Historie geladen" : "Noch nicht geladen"}</span><button className="btn btn-secondary" disabled={technicalState.isSaving} type="button" onClick={onRunEvaluation}>Golden Eval ausführen</button></div>
        </div>
        <div className="dashboard-grid dashboard-grid-4">
          {[
            ["recall_at_k", "Recall@K"],
            ["mrr", "MRR"],
            ["ndcg_at_k", "NDCG"],
            ["no_result_count", "Keine Treffer"]
          ].map(([key, label]) => <article className="metric-card" key={key}><span>{label}</span><strong>{key.endsWith("count") ? numberText(latestEvaluation[key] || 0) : percentText(latestEvaluation[key] || 0)}</strong></article>)}
        </div>
        <div className="content-grid two-columns mt-4">
          <StatsList rows={regressionSignals.map((signal) => [ragText(signal.metric), percentText(signal.current || 0)] as const)} empty={["Golden Eval", "noch keine Runs gespeichert"]} />
          <StatsList rows={evaluationRuns.slice(0, 5).map((run) => [technicalReference("Run", run.id), `${percentText(run.recall_at_k || 0)} Recall / ${percentText(run.mrr || 0)} MRR`] as const)} empty={["Runs", "keine Historie"]} />
        </div>
      </section>
    </section>
  );
}
