import { type ReactNode } from "react";
import { type AdminAiPayload } from "../adminAiApi";
import { objectPayload, technicalDateTime, technicalReference } from "../adminAiTechnicalModel";
import { ragText } from "../adminAiRagBoardModel";
import { ObservabilityLangfuseTraceLink } from "./AdminAiObservabilityLangfuse";
import { DataTable } from "./AdminAiShared";
import { numberText } from "../adminAiFormat";

/**
 * Render the primary observability log table with Langfuse trace links.
 */
export function ObservabilityLogsPanel({
  isLoading,
  logs,
  traceHost
}: {
  readonly isLoading: boolean;
  readonly logs: readonly AdminAiPayload[];
  readonly traceHost: string;
}): ReactNode {
  return (
    <section className="ai-admin-area" id="ai-diagnostics">
      <section className="panel">
        <div className="panel-header">
          <div>
            <h3>KI-Protokolle</h3>
            <p className="panel-meta">Referenz, Qualität, Quellen und Langfuse-Trace je Anfrage.</p>
          </div>
          <span className="badge badge-ai">
            {isLoading ? "lädt" : "geladen"}
          </span>
        </div>
        <DataTable
          caption="AI-Monitoring-Protokolle mit Antwortqualität, Sicherheit und Quellen"
          headers={["Zeit", "Referenz", "Qualität", "Quellen", "Dauer", "Langfuse", "Debug"]}
          rows={logs.map((item) => {
            const langfuseRef = objectPayload(item.langfuse);
            const traceId = ragText(langfuseRef.trace_id);
            return [
              technicalDateTime(item.created_at),
              technicalReference("AI", item.id),
              item.quality_status || item.status,
              item.source_count || 0,
              `${numberText(item.response_duration_ms || item.retrieval_duration_ms || 0)} ms`,
              <ObservabilityLangfuseTraceLink host={traceHost} traceId={traceId} />,
              "Debug"
            ];
          })}
        />
      </section>
    </section>
  );
}
