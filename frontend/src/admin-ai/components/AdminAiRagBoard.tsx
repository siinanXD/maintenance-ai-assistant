import { type ReactNode } from "react";

import { AdminAiSourceTestPanel } from "./AdminAiSourceCheck";
import { type AdminAiRagBoardProps } from "../adminAiRagBoardModel";
import { KnowledgeDocumentsPanel } from "./KnowledgeDocumentsPanel";
import { KnowledgeNetworkPanel } from "./KnowledgeNetworkPanel";
import {
  KnowledgeStatusPanel,
  RagHealthRail,
  RagIndexTrack,
  SourceHealthBoard
} from "./KnowledgeStatusPanel";
import { TrainingEntriesPanel } from "./TrainingEntriesPanel";

/**
 * Render knowledge maintenance and source testing in a simple two-column ops layout.
 */
export function AdminAiRagBoard(props: AdminAiRagBoardProps): ReactNode {
  const { onQueueStale, onReindexStale, ragBoardState } = props;

  return (
    <>
      <section className="ai-admin-area rag-board-area" id="ai-rag-board">
        <div className="rag-ops-layout">
          <div className="rag-ops-primary">
            <div className="rag-ops-toolbar">
              <div>
                <h3>Index & Quellen</h3>
                <p className="panel-meta">
                  {ragBoardState.statusMessage || "Quelle → Textabschnitte → Vektoren → Suchbar → Getestet"}
                </p>
              </div>
              <div className="toolbar rag-action-stack">
                <button
                  className="btn btn-secondary btn-sm"
                  disabled={ragBoardState.isSaving}
                  type="button"
                  onClick={onQueueStale}
                >
                  Job planen
                </button>
                <button
                  className="btn btn-primary btn-sm"
                  disabled={ragBoardState.isSaving}
                  type="button"
                  onClick={onReindexStale}
                >
                  Reindex
                </button>
              </div>
            </div>
            {ragBoardState.errorMessage ? (
              <p className="panel-meta text-error">{ragBoardState.errorMessage}</p>
            ) : null}
            <RagHealthRail state={ragBoardState} />
            <RagIndexTrack state={ragBoardState} />
            <SourceHealthBoard state={ragBoardState} />
          </div>
          <aside className="rag-ops-side" aria-label="Quellen-Test">
            <h3>Antwort-Test</h3>
            <p className="panel-meta">Dry-run oder Live-Test gegen aktuelle Quellen.</p>
            <AdminAiSourceTestPanel {...props} layout="arena" />
          </aside>
        </div>
      </section>

      <section className="ai-admin-area rag-board-details-area" id="ai-knowledge-sources">
        <details className="help-disclosure ui-secondary-panel" open>
          <summary>Pflege-Listen: Dokumente, Training, Netzwerk, Index-Details</summary>
          <div className="help-disclosure-body rag-board-details-body">
            <KnowledgeStatusPanel showSourceBoard={false} state={ragBoardState} />
            <KnowledgeNetworkPanel {...props} />
            <TrainingEntriesPanel {...props} />
            <KnowledgeDocumentsPanel {...props} />
          </div>
        </details>
      </section>
    </>
  );
}
