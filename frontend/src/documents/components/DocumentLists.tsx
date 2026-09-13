import { useMemo, useState, type ReactNode } from "react";

import {
  analyzeMachineManual,
  changeDocumentStatus,
  deleteMachineManual,
  loadDocumentVersions,
  reviewGeneratedDocument,
  summarizeGeneratedDocument,
  summarizeMachineManual
} from "../documentApi";
import type {
  DocumentReview,
  DocumentSummary,
  GeneratedDocument,
  MachineManual,
  MessageState
} from "../documentTypes";
import {
  dateTimeLabel,
  documentErrorMessage,
  documentStatusText,
  generatedDocumentSearchText,
  manualSearchText,
  statusBadgeClass,
  triggerDownload
} from "../documentUtils";

type GeneratedDocumentListProps = {
  readonly documents: readonly GeneratedDocument[];
  readonly onMessage: (message: MessageState) => void;
  readonly onRefresh: () => Promise<void>;
  readonly onReview: (review: DocumentReview) => void;
  readonly onSummary: (summary: DocumentSummary) => void;
  readonly writable: boolean;
};

type ManualListProps = {
  readonly manuals: readonly MachineManual[];
  readonly onRefresh: () => Promise<void>;
  readonly onSummary: (summary: DocumentSummary) => void;
  readonly writable: boolean;
};

/**
 * Render one metadata item.
 */
function RecordMetaItem({ label, value }: { readonly label: string; readonly value: string }): ReactNode {
  return (
    <span>
      <small>{label}</small>
      <strong>{value || "-"}</strong>
    </span>
  );
}

/**
 * Render generated document cards.
 */
export function GeneratedDocumentList(props: GeneratedDocumentListProps): ReactNode {
  const [search, setSearch] = useState("");
  const visibleDocuments = useMemo(() => {
    const query = search.trim().toLowerCase();
    return query ? props.documents.filter((document) => generatedDocumentSearchText(document).includes(query)) : props.documents;
  }, [props.documents, search]);

  return (
    <article className="card app-card mobile-primary-card lg:order-1 lg:col-span-12" id="generated-documents">
      <div className="card-body">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Generierte Dokumente</h2>
            <p className="panel-meta">HTML-Berichte aus abgeschlossenen Aufgaben mit Prüfstatus</p>
          </div>
          <span className="badge badge-status is-open" data-document-count>{props.documents.length} Dokumente</span>
        </div>
        <details className="help-disclosure ui-secondary-panel document-list-help">
          <summary>Hinweis zum Prüfstatus</summary>
          <div className="help-disclosure-body">
            <p className="panel-meta">
              Schwache oder unvollständige Berichte sollten nachgearbeitet werden, bevor sie als verlässliche
              Wissensquelle dienen.
            </p>
          </div>
        </details>
        <div className="list-toolbar">
          <label className="compact-search-field" htmlFor="document-list-search">
            <span>Dokumente suchen</span>
            <input className="input input-bordered input-sm" data-list-search data-list-search-target="[data-document-list]" id="document-list-search" placeholder="Titel, Aufgabe, Bereich, Maschine" value={search} onChange={(event) => setSearch(event.currentTarget.value)} />
          </label>
        </div>
        <div className="record-card-grid document-record-grid" data-document-list data-list-search-items=".record-card">
          {visibleDocuments.length ? visibleDocuments.map((document) => <GeneratedDocumentCard {...props} document={document} key={document.id} />) : (
            <article className="guided-empty-state empty-state">
              <strong>Keine Dokumente gefunden.</strong>
              <p>Nutze Filter, lade ein Dokument hoch oder prüfe abgeschlossene Aufgaben, wenn du einen Bericht erwartest.</p>
            </article>
          )}
        </div>
      </div>
    </article>
  );
}

/**
 * Render one generated document card.
 */
function GeneratedDocumentCard(props: GeneratedDocumentListProps & { readonly document: GeneratedDocument }): ReactNode {
  /**
   * Run a generated-document action with shared error handling.
   */
  async function run(action: () => Promise<void>): Promise<void> {
    try {
      await action();
    } catch (error) {
      props.onMessage({ text: documentErrorMessage(error), error: true });
    }
  }

  return (
    <article className="record-card document-record-card" data-search-text={generatedDocumentSearchText(props.document)}>
      <div className="record-card-header">
        <div>
          <h3 className="record-card-title">{props.document.title || "Wartungsbericht"}</h3>
          <p className="record-card-subtitle">Aufgabe #{props.document.task_id} · {props.document.machine || "Keine Maschine"}</p>
        </div>
        <span className={statusBadgeClass(props.document.status)}>{documentStatusText(props.document.status)}</span>
      </div>
      <div className="record-card-meta">
        <RecordMetaItem label="Bereich" value={props.document.department || "-"} />
        <RecordMetaItem label="Version" value={props.document.version ? `v${props.document.version}` : "-"} />
        <RecordMetaItem label="Erstellt" value={dateTimeLabel(props.document.created_at)} />
      </div>
      <div className="record-card-actions">
        <button className="btn btn-outline btn-sm" type="button" onClick={() => run(async () => props.onReview(await reviewGeneratedDocument(props.document.id)))}>Prüfen</button>
        <button className="btn btn-outline btn-sm" type="button" onClick={() => triggerDownload(props.document.download_url, `maintenance_report_task_${props.document.task_id}.html`)}>HTML</button>
        <button className="btn btn-outline btn-sm" type="button" onClick={() => triggerDownload(props.document.pdf_url, `maintenance_report_task_${props.document.task_id}.pdf`)}>PDF</button>
        <button className="btn btn-outline btn-sm" type="button" onClick={() => run(async () => props.onSummary(await summarizeGeneratedDocument(props.document.id)))}>Zusammenfassung</button>
        <button className="btn btn-outline btn-sm" type="button" onClick={() => run(async () => props.onSummary({ title: "Dokumentversionen", summary_status: "Versionen", summary: (await loadDocumentVersions(props.document.id)).map((version) => `v${version.version_number} - ${dateTimeLabel(version.created_at)}`).join("\n") || "Keine Versionen vorhanden." }))}>Versionen</button>
        {props.writable ? <button className="btn btn-outline btn-sm" type="button" onClick={() => run(async () => { await changeDocumentStatus(props.document.id, "submit-review"); await props.onRefresh(); })}>Prüfung</button> : null}
        {props.writable ? <button className="btn btn-outline btn-sm" type="button" onClick={() => run(async () => { await changeDocumentStatus(props.document.id, "approve"); await props.onRefresh(); })}>Freigeben</button> : null}
        {props.writable ? <button className="btn btn-ghost btn-sm" type="button" onClick={() => run(async () => { await changeDocumentStatus(props.document.id, "reject"); await props.onRefresh(); })}>Ablehnen</button> : null}
      </div>
    </article>
  );
}

/**
 * Render machine manual cards.
 */
export function ManualList(props: ManualListProps): ReactNode {
  return (
    <article className="card app-card mobile-primary-card lg:order-1 lg:col-span-12" id="machine-manuals">
      <div className="card-body">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Maschinenhandbücher</h2>
            <p className="panel-meta">Gespeicherte Handbücher mit Analyse- und Zusammenfassungsstatus</p>
          </div>
          <span className="badge badge-status is-open" data-manual-count>{props.manuals.length} Handbücher</span>
        </div>
        <details className="help-disclosure ui-secondary-panel document-list-help">
          <summary>Hinweis zu Maschinenhandbüchern</summary>
          <div className="help-disclosure-body">
            <p className="panel-meta">
              Maschinenhandbücher liefern technische Details. Je klarer Maschine und Bereich gesetzt sind, desto
              besser werden Treffer und Quellenangaben.
            </p>
          </div>
        </details>
        <div className="record-card-grid document-record-grid" data-manual-list data-list-search-items=".record-card">
          {props.manuals.length ? props.manuals.map((manual) => <ManualCard {...props} key={manual.id} manual={manual} />) : (
            <article className="guided-empty-state empty-state">
              <strong>Keine Handbücher vorhanden.</strong>
              <p>Lade ein Maschinenhandbuch hoch und ordne es Maschine und Bereich zu, damit es als Quelle nutzbar wird.</p>
            </article>
          )}
        </div>
      </div>
    </article>
  );
}

/**
 * Render one machine manual card.
 */
function ManualCard(props: ManualListProps & { readonly manual: MachineManual }): ReactNode {
  /**
   * Run a manual action and surface summary output.
   */
  async function run(action: () => Promise<void>): Promise<void> {
    await action();
  }

  return (
    <article className="record-card document-record-card" data-search-text={manualSearchText(props.manual)}>
      <div className="record-card-header">
        <div>
          <h3 className="record-card-title">{props.manual.title || props.manual.original_filename || "Handbuch"}</h3>
          <p className="record-card-subtitle">{props.manual.machine?.name || "Keine Maschine zugeordnet"}</p>
        </div>
        <span className="badge badge-status is-progress">{props.manual.analysis_status || "nicht geprüft"}</span>
      </div>
      <div className="record-card-meta">
        <RecordMetaItem label="Bereich" value={props.manual.department || "-"} />
        <RecordMetaItem label="Analyse" value={props.manual.analysis_status || "-"} />
        <RecordMetaItem label="Zusammenfassung" value={props.manual.summary_status || "-"} />
      </div>
      <div className="record-card-actions">
        <button className="btn btn-outline btn-sm" type="button" onClick={() => triggerDownload(props.manual.download_url, props.manual.original_filename || "handbuch")}>Download</button>
        <button className="btn btn-outline btn-sm" type="button" onClick={() => run(async () => { props.onSummary(await analyzeMachineManual(props.manual.id)); await props.onRefresh(); })}>Analysieren</button>
        <button className="btn btn-outline btn-sm" type="button" onClick={() => run(async () => { props.onSummary(await summarizeMachineManual(props.manual.id)); await props.onRefresh(); })}>Zusammenfassen</button>
        {props.writable ? <button className="btn btn-ghost btn-sm" type="button" onClick={() => run(async () => { if (!window.confirm(`${props.manual.title || props.manual.original_filename || "Handbuch"} wirklich löschen?`)) return; await deleteMachineManual(props.manual.id); await props.onRefresh(); })}>Löschen</button> : null}
      </div>
    </article>
  );
}
