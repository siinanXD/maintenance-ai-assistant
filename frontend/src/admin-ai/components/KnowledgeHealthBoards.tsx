import { type ReactNode } from "react";
import { type AdminAiRagBoardState, RAG_SOURCE_DEFINITIONS, objectPayload, ragText } from "../adminAiRagBoardModel";
import { numberText } from "../adminAiFormat";
import { ragDateTime } from "../adminAiRagLabels";
import { ragReadinessLabel, sourceHealth, sourceMetrics, vectorStatus } from "../adminAiKnowledgeHealth";

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
      <article className="rag-health-item is-good">
        <span className="rag-health-icon">AI</span>
        <div>
          <small>Systemstatus</small>
          <strong>bereit</strong>
          <em>Betriebsbereit</em>
        </div>
      </article>
      <article className={`rag-health-item ${score >= 80 ? "is-good" : "is-watch"}`}>
        <span className="rag-health-icon">RG</span>
        <div>
          <small>RAG-Bereitschaft</small>
          <strong>{score}/100</strong>
          <em>{ragReadinessLabel(status)}</em>
        </div>
      </article>
      <article className={`rag-health-item ${jobsFailed ? "is-error" : jobsQueued ? "is-watch" : "is-good"}`}>
        <span className="rag-health-icon">Q</span>
        <div>
          <small>Queue</small>
          <strong>{state.jobs.length} Jobs</strong>
          <em>{jobsQueued} wartend / {jobsFailed} fehlgeschlagen</em>
        </div>
      </article>
      <article className="rag-health-item">
        <span className="rag-health-icon">$</span>
        <div>
          <small>Kosten</small>
          <strong>$0</strong>
          <em>in Effektivität</em>
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
    <div className={compact ? "ai-source-grid" : "rag-game-board"} aria-label="RAG Quellen-Spielbrett">
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
