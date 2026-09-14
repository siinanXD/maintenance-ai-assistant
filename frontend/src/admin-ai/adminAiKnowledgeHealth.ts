import { type AdminAiPayload } from "./adminAiApi";
import { numberText } from "./adminAiFormat";
import { objectPayload, ragText } from "./adminAiRagBoardModel";

/**
 * Return source metrics for a group of source types.
 */
export function sourceMetrics(
  knowledgeStatus: AdminAiPayload | null,
  types: readonly string[]
): { readonly active: boolean; readonly chunks: number; readonly documents: number; readonly searchable: number } {
  const sourceTypes = Array.isArray(knowledgeStatus?.source_types)
    ? knowledgeStatus.source_types.filter((item): item is AdminAiPayload => typeof item === "object" && item !== null)
    : [];

  return sourceTypes
    .filter((item) => types.includes(ragText(item.source_type, "")))
    .reduce<{ readonly active: boolean; readonly chunks: number; readonly documents: number; readonly searchable: number }>(
      (result, item) => ({
        active: result.active || Boolean(item.searchable),
        chunks: result.chunks + Number(item.chunks || 0),
        documents: result.documents + Number(item.documents || 0),
        searchable: result.searchable + Number(item.searchable_documents || 0)
      }),
      { active: false, chunks: 0, documents: 0, searchable: 0 }
    );
}

/**
 * Return health label and tone for one source group.
 */
export function sourceHealth(
  metrics: ReturnType<typeof sourceMetrics>,
  ragEnabled: boolean
): { readonly className: string; readonly detail: string; readonly label: string; readonly ratio: number } {
  const ratio = metrics.documents ? metrics.searchable / metrics.documents : 0;
  if (!ragEnabled) {
    return { className: "is-muted", detail: "Strukturierte Daten bleiben nutzbar", label: "RAG aus", ratio };
  }
  if (!metrics.documents) {
    return { className: "is-muted", detail: "noch keine Quelle registriert", label: "leer", ratio };
  }
  if (metrics.active && ratio >= 0.85) {
    return { className: "is-active", detail: "vollständig im Quellenabruf nutzbar", label: "gesund", ratio };
  }
  if (metrics.active || ratio >= 0.6) {
    return { className: "is-stale", detail: "ein Teil ist suchbar", label: "Achtung", ratio };
  }
  return { className: "is-error", detail: "nicht im RAG-Kontext verfügbar", label: "kritisch", ratio };
}

/**
 * Return the RAG readiness badge label.
 */
export function ragReadinessLabel(knowledgeStatus: AdminAiPayload | null): string {
  const diagnostics = objectPayload(knowledgeStatus?.diagnostics);
  return diagnostics.ready ? "bereit" : "nicht bereit";
}

/**
 * Return the vector status object from the knowledge status payload.
 */
export function vectorStatus(knowledgeStatus: AdminAiPayload | null): AdminAiPayload {
  return objectPayload(knowledgeStatus?.vector_store);
}

/**
 * Return lifecycle object from the knowledge status payload.
 */
export function lifecycleStatus(knowledgeStatus: AdminAiPayload | null): AdminAiPayload {
  return objectPayload(knowledgeStatus?.lifecycle);
}

/**
 * Return a lifecycle KPI value.
 */
export function lifecycleKpiValue(lifecycle: AdminAiPayload, key: string): string {
  const reviewQueue = objectPayload(lifecycle.review_queue);
  const qualityGate = objectPayload(lifecycle.rag_quality_gate);
  if (key === "needs_admin_approval") return numberText(reviewQueue.needs_admin_approval || 0);
  if (key === "non_approved_indexed_documents") {
    return numberText(qualityGate.non_approved_indexed_documents || 0);
  }
  return numberText(lifecycle[key] || 0);
}
