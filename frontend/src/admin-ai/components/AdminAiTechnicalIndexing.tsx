import { type ReactNode } from "react";
import {
  type AdminAiTechnicalProps,
  objectPayload,
  technicalDateTime,
  technicalJobRows
} from "../adminAiTechnicalModel";
import { ragText } from "../adminAiRagBoardModel";
import {
  DataTable,
  isPayload,
  MetricCard,
  StatsList
} from "./AdminAiShared";
import { numberText, percentText } from "../adminAiFormat";

/**
 * Render reindex command, background job and operations panels.
 */
export function IndexingSection({
  onQueueStale,
  onReindexAll,
  onReindexStale,
  technicalState
}: AdminAiTechnicalProps): ReactNode {
  const operations = technicalState.operations || {};
  const database = objectPayload(operations.database);
  const backgroundJobs = objectPayload(operations.background_jobs);
  const ai = objectPayload(operations.ai);
  const rag = objectPayload(operations.rag);
  const requests = objectPayload(operations.requests);
  const slowEndpoints = Array.isArray(requests.slow_endpoints) ? requests.slow_endpoints.filter(isPayload) : [];
  const jobRows = technicalJobRows(technicalState.jobs);
  const statusCounts = technicalState.jobs.reduce<Record<string, number>>((counts, job) => {
    const key = ragText(job.status, "unknown");
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});

  return (
    <section className="ai-admin-area" id="ai-indexing-status">
      <div className="ai-admin-area-header"><div><span className="section-kicker">7. Indexstatus</span><h3>Index-Aufbau, Textabschnitte, Vektoren und Verarbeitung-Jobs</h3><p className="panel-meta">Reindex-Aktionen, Queue, Vektor-Sync und Textabschnitt-Abdeckung sichtbar getrennt vom normalen Antwortverhalten.</p></div><span className="badge badge-ai">{technicalState.isLoading ? "Jobs werden geladen" : "Jobs geladen"}</span></div>
      <section className="panel ai-reindex-command-panel"><div className="panel-header"><div><h3>Reindex-Kommandos</h3><p className="panel-meta">Direkter Reindex blockiert den Request; Job einplanen nutzt die Background-Queue.</p></div><span className="panel-meta">{technicalState.statusMessage}</span></div><div className="ai-admin-actions"><button className="btn btn-primary" disabled={technicalState.isSaving} type="button" onClick={onReindexAll}>Wissen neu indexieren</button><button className="btn btn-secondary" disabled={technicalState.isSaving} type="button" onClick={onReindexStale}>Nur veraltete indexieren</button><button className="btn btn-ghost" disabled={technicalState.isSaving} type="button" onClick={onQueueStale}>Job einplanen</button></div></section>
      <section className="panel"><div className="panel-header"><div><h3>Background Jobs</h3><p className="panel-meta">RAG-Reindex und Wartungsdiagnose-Aufgaben mit Status und Ergebnis.</p></div><span className="panel-meta">{technicalState.jobs.length} Jobs</span></div><DataTable caption="Background-Jobs für RAG-Reindex und Wartungsdiagnose" headers={["ID", "Typ", "Status", "Versuche", "Ergebnis"]} rows={jobRows} /></section>
      <section className="panel"><div className="panel-header"><div><h3>Operationsdiagnose</h3><p className="panel-meta">Queue, DB-Latenz, AI-Latenz, Jobdauer und langsame Endpoints.</p></div><span className="panel-meta">{technicalDateTime(operations.generated_at)}</span></div><div className="dashboard-grid dashboard-grid-4">
        <MetricCard label="DB Latenz" value={`${numberText(database.latency_ms || 0)} ms`} />
        <MetricCard label="Queue" value={backgroundJobs.queue_length || 0} />
        <MetricCard label="Laufend" value={backgroundJobs.running || 0} />
        <MetricCard label="Fehlgeschlagen" value={backgroundJobs.failed || 0} />
        <MetricCard label="AI Latenz" value={`${numberText(ai.avg_latency_ms || 0)} ms`} />
        <MetricCard label="RAG stale" value={percentText(rag.stale_ratio || 0)} />
        <MetricCard label="Ältester Job" value={`${numberText(backgroundJobs.oldest_queued_age_seconds || 0)} s`} />
        <MetricCard label="Job Dauer" value={`${numberText(backgroundJobs.recent_avg_duration_seconds || 0)} s`} />
      </div><div className="content-grid two-columns mt-4"><StatsList rows={[["Queued", statusCounts.queued || 0], ["Running", statusCounts.running || 0], ["Failed", statusCounts.failed || 0], ["Done", statusCounts.done || 0]]} /><StatsList rows={slowEndpoints.map((item) => [item.endpoint, `${ragText(item.avg_duration_ms)} ms avg / ${ragText(item.slow_count)} slow`] as const)} empty={["Slow Endpoints", "noch keine Messwerte"]} /></div></section>
    </section>
  );
}
