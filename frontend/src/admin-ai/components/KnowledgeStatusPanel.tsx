import { type ReactNode } from "react";
import { type AdminAiRagBoardState, objectPayload, ragText } from "../adminAiRagBoardModel";
import { isPayload } from "./AdminAiRagBoardShared";
import { numberText } from "../adminAiFormat";
import { StatsList } from "./AdminAiShared";
import { SourceHealthBoard } from "./KnowledgeHealthBoards";
import { lifecycleKpiValue, lifecycleStatus, ragReadinessLabel, vectorStatus } from "../adminAiKnowledgeHealth";
import { ragDateTime, sourceTypeLabel } from "../adminAiRagLabels";

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
        <span className="badge badge-ai">{ragReadinessLabel(status)}</span>
      </div>
      <div className="dashboard-grid dashboard-grid-4">
        {["documents", "indexed", "stale", "pending", "searchable_documents", "chunks"].map((key) => (
          <article className="metric-card" key={key}>
            <span>{key}</span>
            <strong>{numberText(status?.[key] || 0)}</strong>
          </article>
        ))}
        <article className="metric-card">
          <span>Bereitschaft</span>
          <strong>{numberText(status?.readiness_score || 0)}/100</strong>
        </article>
      </div>
      <div className="content-grid two-columns mt-4">
        <StatsList rows={sourceTypes.map((item) => [
          sourceTypeLabel(item.source_type),
          `${numberText(item.searchable_documents || 0)}/${numberText(item.documents || 0)} durchsuchbar, ${numberText(item.chunks || 0)} Textabschnitte`
        ] as const)} empty={["Quellen", "Noch keine Daten indexiert"]} />
        <StatsList rows={[
          ["RAG aktiv", diagnostics.rag_enabled ? "ja" : "nein"],
          ["Suchindex", diagnostics.vector_store],
          ["Embedding-Anbieter", diagnostics.embedding_provider],
          ["Textabschnitting", `${ragText(diagnostics.chunk_size)} / ${ragText(diagnostics.chunk_overlap)}`],
          ["Genutzte Quellen pro Antwort", diagnostics.top_k],
          ["Maximal geprüfte Quellen", diagnostics.scan_limit]
        ]} />
      </div>
      <div className="content-grid two-columns mt-4">
        <StatsList rows={reasons.map((reason) => ["Bereitschaft", reason] as const)} empty={["Bereitschaft", "Keine Bereitschaft-Daten vorhanden."]} />
        <StatsList rows={problems.map((documentItem) => [
          `#${ragText(documentItem.id)} ${sourceTypeLabel(documentItem.source_type)}`,
          `${ragText(documentItem.status)} - ${ragText(documentItem.title)}`
        ] as const)} empty={["Problemdokumente", "keine offenen Quellen"]} />
      </div>
      <div className="content-grid two-columns mt-4">
        <StatsList rows={syncRows} />
        <StatsList rows={issueRows} />
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
    <section className="panel">
      <div className="panel-header">
        <div>
          <h3>Wissens-Lebenszyklus</h3>
          <p className="panel-meta">Qualitätsstatus, Prüf-Gates und Freigaben der indexierbaren Wissensbasis.</p>
        </div>
        <span className={`badge badge-ai ${hasProblems ? "is-error" : hasReview ? "is-stale" : "is-active"}`}>
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
            <strong>{lifecycleKpiValue(lifecycle, key)}</strong>
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
        ]} />
        <StatsList rows={[
          ["Quality Gate", qualityGate.enabled ? "aktiv" : "diagnostisch"],
          ["Freigegeben indexiert", qualityGate.approved_indexed_documents || 0],
          ["Nicht freigegeben indexiert", qualityGate.non_approved_indexed_documents || 0],
          ["Hinweis", qualityGate.reason || "-"]
        ]} />
      </div>
      <div className="content-grid two-columns mt-4">
        <StatsList rows={nextActions.slice(0, 6).map((action, index) => [`Aktion ${index + 1}`, action])} empty={["Aktionen", "Keine offenen Lifecycle-Aktionen."]} />
        <StatsList rows={steps.slice(0, 9).map((step) => [ragText(step.label), ragText(step.status)])} empty={["Lifecycle", "keine Diagnostik vorhanden"]} />
      </div>
    </section>
  );
}
