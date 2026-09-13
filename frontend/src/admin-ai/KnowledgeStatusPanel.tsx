import { type ReactNode } from "react";

import {
  type AdminAiRagBoardState,
  RAG_SOURCE_DEFINITIONS,
  lifecycleKpiValue,
  lifecycleStatus,
  objectPayload,
  ragDateTime,
  ragReadinessLabel,
  ragText,
  sourceHealth,
  sourceMetrics,
  sourceTypeLabel,
  vectorStatus
} from "./adminAiRagBoardModel";
import { numberText } from "./adminAiEffectivenessModel";
import { isPayload, StatsList } from "./AdminAiRagBoardShared";

type KnowledgeStatusPanelProps = {
  readonly showSourceBoard?: boolean;
  readonly state: AdminAiRagBoardState;
};

/**
 * Render the complete knowledge status block.
 */
export function KnowledgeStatusPanel({
  showSourceBoard = true,
  state
}: KnowledgeStatusPanelProps): ReactNode {
  return (
    <>
      {showSourceBoard ? (
        <section className="panel">
          <div className="panel-header">
            <div>
              <h3>Quelle Health Matrix</h3>
              <p className="panel-meta">Einträge, Textabschnitte, RAG-Aktivierung und Health je Quelle.</p>
            </div>
          </div>
          <SourceHealthBoard state={state} compact />
        </section>
      ) : null}
      <details className="help-disclosure ui-secondary-panel rag-status-disclosure">
        <summary>Index-Status und Lifecycle-Details</summary>
        <div className="help-disclosure-body rag-status-disclosure-body">
          <RagStatusPanel state={state} />
          <KnowledgeLifecyclePanel state={state} />
        </div>
      </details>
    </>
  );
}

/**
 * Render the left-rail system status list for the RAG board shell.
 */
export function RagHealthRail({ state }: { readonly state: AdminAiRagBoardState }): ReactNode {
  const status = state.knowledgeStatus;
  const score = Number(status?.readiness_score || 0);
  const jobsQueued = state.jobs.filter((job) => job.status === "queued").length;
  const jobsFailed = state.jobs.filter((job) => job.status === "failed").length;

  return (
    <div className="rag-health-list" aria-label="Systemstatus">
      <article className="rag-health-item is-good" data-ai-health="ai">
        <span className="rag-health-icon">AI</span>
        <div>
          <small>Systemstatus</small>
          <strong data-ai-health-label>bereit</strong>
          <em data-ai-health-detail>Betriebsbereit</em>
        </div>
      </article>
      <article className={`rag-health-item ${score >= 80 ? "is-good" : "is-watch"}`} data-ai-health="rag">
        <span className="rag-health-icon">RG</span>
        <div>
          <small>RAG-Bereitschaft</small>
          <strong data-ai-health-label>{score}/100</strong>
          <em data-ai-health-detail>{ragReadinessLabel(status)}</em>
        </div>
      </article>
      <article className={`rag-health-item ${jobsFailed ? "is-error" : jobsQueued ? "is-watch" : "is-good"}`} data-ai-health="queue">
        <span className="rag-health-icon">Q</span>
        <div>
          <small>Queue</small>
          <strong data-ai-job-count>{state.jobs.length} Jobs</strong>
          <em data-ai-health-detail>{jobsQueued} wartend / {jobsFailed} fehlgeschlagen</em>
        </div>
      </article>
      <article className="rag-health-item">
        <span className="rag-health-icon">$</span>
        <div>
          <small>Kosten</small>
          <strong data-ai-kpi="estimated_cost_usd">$0</strong>
          <em data-ai-price-status>in Effektivität</em>
        </div>
      </article>
    </div>
  );
}

/**
 * Render the index pipeline track above the source board.
 */
export function RagIndexTrack({ state }: { readonly state: AdminAiRagBoardState }): ReactNode {
  const status = state.knowledgeStatus;
  const documents = Number(status?.documents || 0);
  const chunks = Number(status?.chunks || 0);
  const searchable = Number(status?.searchable_documents || 0);
  const readiness = Number(status?.readiness_score || 0);
  const steps = [
    { key: "source", label: "Quelle", value: numberText(documents), done: documents > 0 },
    { key: "chunks", label: "Textabschnitte", value: numberText(chunks), done: chunks > 0 },
    { key: "vectors", label: "Vektoren", value: numberText(status?.indexed || 0), done: Number(status?.indexed || 0) > 0 },
    { key: "search", label: "Suchbar", value: numberText(searchable), done: searchable > 0 },
    { key: "tested", label: "Getestet", value: `${readiness}%`, done: readiness >= 80 }
  ] as const;

  return (
    <div className="rag-index-track-panel">
      <div className="rag-index-track" aria-label="RAG Pipeline">
        {steps.map((step) => (
          <article className={step.done ? "is-done" : ""} key={step.key}>
            <span>{step.label}</span>
            <strong>{step.value}</strong>
            {step.done ? <b aria-hidden="true">✓</b> : null}
          </article>
        ))}
      </div>
    </div>
  );
}

/**
 * Render source health cards from the knowledge status payload.
 */
export function SourceHealthBoard({
  compact = false,
  state
}: {
  readonly compact?: boolean;
  readonly state: AdminAiRagBoardState;
}): ReactNode {
  const diagnostics = objectPayload(state.knowledgeStatus?.diagnostics);
  const ragEnabled = Boolean(diagnostics.rag_enabled);
  const vector = vectorStatus(state.knowledgeStatus);
  const lastUpdate = vector.latest_indexed_at || objectPayload(vector.last_successful_sync).synced_at || "";

  return (
    <div className={compact ? "ai-source-grid" : "rag-game-board"} data-ai-source-health aria-label="RAG Quellen-Spielbrett">
      {RAG_SOURCE_DEFINITIONS.map((definition) => {
        const metrics = sourceMetrics(state.knowledgeStatus, definition.types);
        const health = sourceHealth(metrics, ragEnabled);
        const scorePercent = Math.round((health.ratio || 0) * 100);

        return (
          <article className={`ai-source-card ${health.className}`} key={definition.key}>
            <div className="ai-source-card-header">
              <strong>{definition.label}</strong>
              <span className={`status-pill ${health.className}`}>{health.label}</span>
            </div>
            <div className="ai-source-score">
              <strong>{numberText(scorePercent)}%</strong>
              <small>Gesundheit</small>
            </div>
            <p>{definition.description}</p>
            <div className="ai-source-stats">
              <span><small>Quellen</small><strong>{numberText(metrics.documents)}</strong></span>
              <span><small>Chunks</small><strong>{numberText(metrics.chunks)}</strong></span>
              <span><small>Suchbar</small><strong>{numberText(metrics.searchable)}</strong></span>
            </div>
            <small>
              Embedding: {ragText(diagnostics.embedding_provider)} · RAG: {metrics.active ? "aktiv genutzt" : "nicht aktiv"} ·
              Letzte Aktualisierung: {lastUpdate ? ragDateTime(lastUpdate) : "nicht verfügbar"} · Health: {health.detail}
            </small>
          </article>
        );
      })}
    </div>
  );
}

/**
 * Render RAG readiness and vector sync status.
 */
function RagStatusPanel({ state }: { readonly state: AdminAiRagBoardState }): ReactNode {
  const status = state.knowledgeStatus;
  const diagnostics = objectPayload(status?.diagnostics);
  const vector = vectorStatus(status);
  const sourceTypes = Array.isArray(status?.source_types) ? status.source_types.filter(isPayload) : [];
  const problems = Array.isArray(status?.problem_documents) ? status.problem_documents.filter(isPayload) : [];
  const reasons = Array.isArray(status?.readiness_reasons) ? status.readiness_reasons : [];
  const syncRows: readonly (readonly [unknown, unknown])[] = [
    ["Suchindex Backend", vector.store],
    ["Konfiguriert", vector.configured_store],
    ["Ausweichbetrieb", vector.fallback_active ? "aktiv" : "nein"],
    ["Soll Vektoren", numberText(vector.expected_vector_count || 0)],
    ["Ist Vektoren", vector.actual_vector_count == null ? "-" : numberText(vector.actual_vector_count)],
    ["Letzter Index", ragDateTime(vector.latest_indexed_at)]
  ];
  const issueRows: readonly (readonly [unknown, unknown])[] = [
    ["Reindex empfohlen", vector.reindex_recommended ? "ja" : "nein"],
    ["Stale Dokumente", numberText(vector.stale_document_count || 0)],
    ["Fehlende Textabschnitte", numberText(vector.missing_chunk_count || 0)],
    ["Textabschnitt Mismatch", numberText(vector.chunk_mismatch_count || 0)],
    ["Sync-Fehler", numberText(vector.vector_sync_failure_count || 0)]
  ];

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h3>RAG-Index Status</h3>
          <p className="panel-meta">Bereitschaft, Vektor-Sync, Problemquellen und Indexabdeckung.</p>
        </div>
        <span className="badge badge-ai" data-rag-readiness>{ragReadinessLabel(status)}</span>
      </div>
      <div className="dashboard-grid dashboard-grid-4">
        {["documents", "indexed", "stale", "pending", "searchable_documents", "chunks"].map((key) => (
          <article className="metric-card" key={key}>
            <span>{key}</span>
            <strong data-rag-kpi={key}>{numberText(status?.[key] || 0)}</strong>
          </article>
        ))}
        <article className="metric-card">
          <span>Bereitschaft</span>
          <strong data-rag-readiness-score>{numberText(status?.readiness_score || 0)}/100</strong>
        </article>
      </div>
      <div className="content-grid two-columns mt-4">
        <StatsList rows={sourceTypes.map((item) => [
          sourceTypeLabel(item.source_type),
          `${numberText(item.searchable_documents || 0)}/${numberText(item.documents || 0)} durchsuchbar, ${numberText(item.chunks || 0)} Textabschnitte`
        ] as const)} empty={["Quellen", "Noch keine Daten indexiert"]} target="source-status" />
        <StatsList rows={[
          ["RAG aktiv", diagnostics.rag_enabled ? "ja" : "nein"],
          ["Suchindex", diagnostics.vector_store],
          ["Embedding-Anbieter", diagnostics.embedding_provider],
          ["Textabschnitting", `${ragText(diagnostics.chunk_size)} / ${ragText(diagnostics.chunk_overlap)}`],
          ["Genutzte Quellen pro Antwort", diagnostics.top_k],
          ["Maximal geprüfte Quellen", diagnostics.scan_limit]
        ]} target="diagnostics" />
      </div>
      <div className="content-grid two-columns mt-4">
        <StatsList rows={reasons.map((reason) => ["Bereitschaft", reason] as const)} empty={["Bereitschaft", "Keine Bereitschaft-Daten vorhanden."]} target="reasons" />
        <StatsList rows={problems.map((documentItem) => [
          `#${ragText(documentItem.id)} ${sourceTypeLabel(documentItem.source_type)}`,
          `${ragText(documentItem.status)} - ${ragText(documentItem.title)}`
        ] as const)} empty={["Problemdokumente", "keine offenen Quellen"]} target="problems" />
      </div>
      <div className="content-grid two-columns mt-4">
        <StatsList rows={syncRows} target="vector-sync" />
        <StatsList rows={issueRows} target="vector-issues" />
      </div>
    </section>
  );
}

/**
 * Render knowledge lifecycle review.
 */
function KnowledgeLifecyclePanel({ state }: { readonly state: AdminAiRagBoardState }): ReactNode {
  const lifecycle = lifecycleStatus(state.knowledgeStatus);
  const reviewQueue = objectPayload(lifecycle.review_queue);
  const qualityGate = objectPayload(lifecycle.rag_quality_gate);
  const nextActions = Array.isArray(lifecycle.next_actions) ? lifecycle.next_actions : [];
  const steps = Array.isArray(lifecycle.steps) ? lifecycle.steps.filter(isPayload) : [];
  const hasProblems = Number(lifecycle.problem_documents || 0) > 0;
  const hasReview = Object.values(reviewQueue).some((value) => Number(value || 0) > 0);

  return (
    <section className="panel" data-knowledge-lifecycle-panel>
      <div className="panel-header">
        <div>
          <h3>Wissens-Lebenszyklus</h3>
          <p className="panel-meta">Qualitätsstatus, Prüf-Gates und Freigaben der indexierbaren Wissensbasis.</p>
        </div>
        <span className={`badge badge-ai ${hasProblems ? "is-error" : hasReview ? "is-stale" : "is-active"}`} data-knowledge-lifecycle-state>
          {hasProblems ? "kritisch" : hasReview ? "Review offen" : "bereit"}
        </span>
      </div>
      <div className="dashboard-grid dashboard-grid-4">
        {[
          "drafts",
          "technician_confirmed",
          "admin_approved",
          "problem_documents",
          "feedback_open",
          "knowledge_gaps_open",
          "needs_admin_approval",
          "non_approved_indexed_documents"
        ].map((key) => (
          <article className="metric-card" key={key}>
            <span>{key}</span>
            <strong data-lifecycle-kpi={key}>{lifecycleKpiValue(lifecycle, key)}</strong>
          </article>
        ))}
      </div>
      <div className="content-grid two-columns mt-4">
        <StatsList rows={[
          ["Techniker-Review", reviewQueue.needs_technician_review || 0],
          ["Admin-Freigabe", reviewQueue.needs_admin_approval || 0],
          ["Quality-Review", reviewQueue.needs_quality_review || 0],
          ["Low Quality", reviewQueue.low_quality || 0],
          ["Duplikate", reviewQueue.duplicate || 0],
          ["Refresh", reviewQueue.needs_refresh || 0],
          ["Abgelehnt", reviewQueue.rejected || 0]
        ]} target="lifecycle-review" />
        <StatsList rows={[
          ["Quality Gate", qualityGate.enabled ? "aktiv" : "diagnostisch"],
          ["Freigegeben indexiert", qualityGate.approved_indexed_documents || 0],
          ["Nicht freigegeben indexiert", qualityGate.non_approved_indexed_documents || 0],
          ["Hinweis", qualityGate.reason || "-"]
        ]} target="lifecycle-gate" />
      </div>
      <div className="content-grid two-columns mt-4">
        <StatsList rows={nextActions.slice(0, 6).map((action, index) => [`Aktion ${index + 1}`, action])} empty={["Aktionen", "Keine offenen Lifecycle-Aktionen."]} target="lifecycle-actions" />
        <StatsList rows={steps.slice(0, 9).map((step) => [ragText(step.label), ragText(step.status)])} empty={["Lifecycle", "keine Diagnostik vorhanden"]} target="lifecycle-steps" />
      </div>
    </section>
  );
}
