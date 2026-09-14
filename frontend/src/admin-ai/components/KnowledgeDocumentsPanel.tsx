import { type FormEvent, useState, type ReactNode } from "react";
import { ActionDrawer } from "../../components/ui/ActionDrawer";
import { PageActionBar } from "../../components/ui/PageActionBar";
import { createActionDefinition } from "../../components/ui/createActionSchema";
import { type AdminAiRagBoardProps, QUALITY_STATUSES, ragText } from "../adminAiRagBoardModel";
import {
  filterChange,
  onUpdateQualityClick,
  QUALITY_OPTIONS,
  SelectFilter,
  SOURCE_OPTIONS,
  submitUpload
} from "./AdminAiRagBoardShared";
import { numberText } from "../adminAiFormat";
import { qualityStatusClass, qualityStatusLabel, sourceTypeLabel } from "../adminAiRagLabels";

/**
 * Render the knowledge database filters and table.
 */
export function KnowledgeDocumentsPanel(props: AdminAiRagBoardProps): ReactNode {
  const { onDeleteKnowledge, onKnowledgeFilterChange, onKnowledgeUpload, onQueueDocument, onReindexDocument, onUpdateKnowledgeQuality, ragBoardState } = props;
  const [isUploadDrawerOpen, setIsUploadDrawerOpen] = useState(false);
  const filters = ragBoardState.filters;

  return (
    <>
      <section className="panel">
        <div className="panel-header">
          <div><h3>Wissensdatenbank</h3><p className="panel-meta">Dokumente, Trainingseinträge und automatisch erzeugte Quellen verwalten.</p></div>
          <div className="toolbar admin-ai-toolbar">
            <input className="input input-bordered" placeholder="Wissen durchsuchen" value={filters.knowledgeQuery} onChange={filterChange(onKnowledgeFilterChange, "knowledgeQuery")} />
            <SelectFilter value={filters.knowledgeSource} onChange={filterChange(onKnowledgeFilterChange, "knowledgeSource")} options={SOURCE_OPTIONS} />
            <select className="input input-bordered" aria-label="Wissen nach Indexstatus filtern" value={filters.knowledgeStatus} onChange={filterChange(onKnowledgeFilterChange, "knowledgeStatus")}>
              <option value="">Alle Status</option><option value="indexed">Indexiert</option><option value="stale">Veraltet</option><option value="pending">Ausstehend</option><option value="error">Fehler</option><option value="no_text">Ohne Text</option>
            </select>
            <SelectFilter ariaLabel="Wissen nach Qualitätsstatus filtern" value={filters.knowledgeQuality} onChange={filterChange(onKnowledgeFilterChange, "knowledgeQuality")} options={QUALITY_OPTIONS} />
            <PageActionBar
              label="Wissensdatenbank Aktionen"
              actions={[
                {
                  disabled: ragBoardState.isSaving,
                  onClick: () => setIsUploadDrawerOpen(true),
                  schema: createActionDefinition("adminKnowledgeUpload"),
                  variant: "primary"
                }
              ]}
            />
          </div>
          <div className="knowledge-origin-legend" aria-label="Herkunft der Wissensquellen">
            <span className="status-pill is-source-automatic">Automatisch</span>
            <span className="status-pill is-source-manual">Manuell</span>
            <span className="status-pill is-source-prebuilt">Vorgefertigt</span>
          </div>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <caption>Wissensdatenbank mit Quelle, Indexstatus, Qualität, Textabschnitte und Abteilung</caption>
            <thead><tr><th scope="col">Titel</th><th scope="col">Quelle</th><th scope="col">Index</th><th scope="col">Qualität</th><th scope="col">Textabschnitte</th><th scope="col">Abteilung</th><th scope="col">Aktionen</th></tr></thead>
            <tbody>
              {ragBoardState.knowledge.length ? ragBoardState.knowledge.map((documentItem) => (
                <tr key={ragText(documentItem.id)}>
                  <td>{ragText(documentItem.title)}</td>
                  <td className="knowledge-source-cell"><span className="status-pill is-muted">{sourceTypeLabel(documentItem.source_type)}</span></td>
                  <td>{ragText(documentItem.status)}</td>
                  <td><span className={`status-pill ${qualityStatusClass(documentItem.quality_status)}`}>{qualityStatusLabel(documentItem.quality_status)}</span></td>
                  <td>{numberText(documentItem.chunk_count || 0)}</td>
                  <td>{ragText(documentItem.department)}</td>
                  <td className="table-actions">
                    <button className="btn btn-secondary btn-sm" type="button" onClick={() => onReindexDocument(Number(documentItem.id))}>Indexieren</button>
                    <button className="btn btn-ghost btn-sm" type="button" onClick={() => onQueueDocument(Number(documentItem.id))}>Job planen</button>
                    <select className="input input-bordered" data-knowledge-quality-select={ragText(documentItem.id)} aria-label="Wissens-Qualitätsstatus setzen" defaultValue={ragText(documentItem.quality_status, "draft")}>
                      {QUALITY_STATUSES.map((status) => <option value={status} key={status}>{qualityStatusLabel(status)}</option>)}
                    </select>
                    <button className="btn btn-secondary btn-sm" type="button" onClick={(event) => onUpdateQualityClick(event, onUpdateKnowledgeQuality, Number(documentItem.id))}>Status setzen</button>
                    <button className="btn btn-ghost btn-sm" type="button" onClick={() => onDeleteKnowledge(Number(documentItem.id))}>Löschen</button>
                  </td>
                </tr>
              )) : <tr><td colSpan={7}>Keine Wissensquellen für diesen Filter.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
      <ActionDrawer
        definition={createActionDefinition("adminKnowledgeUpload")}
        isOpen={isUploadDrawerOpen}
        onClose={() => setIsUploadDrawerOpen(false)}
      >
        <KnowledgeUploadForm isSaving={ragBoardState.isSaving} onKnowledgeUpload={onKnowledgeUpload} />
      </ActionDrawer>
    </>
  );
}

/**
 * Render the admin knowledge upload form inside the shared action drawer.
 */
function KnowledgeUploadForm({
  isSaving,
  onKnowledgeUpload
}: {
  readonly isSaving: boolean;
  readonly onKnowledgeUpload: (form: HTMLFormElement) => void;
}): ReactNode {
  /**
   * Forward the upload form to the existing admin action handler.
   */
  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    submitUpload(event, onKnowledgeUpload);
  }

  return (
    <form className="stack" onSubmit={handleSubmit}>
      <input className="input input-bordered" name="department" placeholder="Abteilung optional" />
      <input className="input input-bordered" name="file" type="file" accept=".pdf,.txt,.html,.htm" />
      <button className="btn btn-primary" disabled={isSaving} type="submit">Hochladen</button>
    </form>
  );
}
