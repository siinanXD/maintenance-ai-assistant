import { useState, type FormEvent, type ReactNode } from "react";

import { checkUploadedDocument, uploadMachineManual } from "../documentApi";
import type {
  DocumentReview,
  DocumentSummary,
  Machine,
  MessageState,
  ReviewFinding
} from "../documentTypes";
import { documentErrorMessage, reviewStatusText, statusBadgeClass } from "../documentUtils";

type UploadCheckPanelProps = {
  readonly onReview: (review: DocumentReview) => void;
};

type ManualUploadPanelProps = {
  readonly machines: readonly Machine[];
  readonly onUploaded: () => Promise<void>;
};

type ReviewPanelProps = {
  readonly review: DocumentReview | null;
};

type SummaryPanelProps = {
  readonly summary: DocumentSummary | null;
};

/**
 * Render upload check controls.
 */
export function UploadCheckPanel({ onReview }: UploadCheckPanelProps): ReactNode {
  const [message, setMessage] = useState<MessageState>({ text: "", error: false });

  /**
   * Submit a temporary document check.
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    if (!formData.get("file")) {
      setMessage({ text: "Bitte eine HTML- oder TXT-Datei auswählen.", error: true });
      return;
    }
    setMessage({ text: "Dokument wird geprüft...", error: false });
    try {
      const review = await checkUploadedDocument(formData);
      onReview(review);
      setMessage({ text: "Dokument geprüft.", error: false });
    } catch (error) {
      setMessage({ text: documentErrorMessage(error), error: true });
    }
  }

  return (
    <article className="card app-card lg:order-4 lg:col-span-12">
      <form onSubmit={handleSubmit}>
        <div className="card-body">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Hochladen prüfen</h2>
              <p className="panel-meta">HTML- oder TXT-Bericht prüfen, ohne ihn zu speichern</p>
            </div>
            <span className="badge badge-ai">Prüfung</span>
          </div>
          <div className="status-explainer">
            <p><strong>Hochladeprüfung:</strong> Die Datei wird auf Vollständigkeit und Nutzbarkeit geprüft, ohne sie dauerhaft zu speichern.</p>
          </div>
          <div className="upload-check-panel">
            <div className="field">
              <label htmlFor="document-check-file">Dokument</label>
              <input className="input input-bordered" id="document-check-file" name="file" type="file" accept=".html,.htm,.txt,text/html,text/plain" />
            </div>
            <div className="toolbar">
              <button className="btn btn-primary" type="submit">Dokument prüfen</button>
              <span className={`panel-meta${message.error ? " is-error" : ""}`}>{message.text}</span>
            </div>
          </div>
        </div>
      </form>
    </article>
  );
}

/**
 * Render manual upload controls.
 */
export function ManualUploadPanel({ machines, onUploaded }: ManualUploadPanelProps): ReactNode {
  const [message, setMessage] = useState<MessageState>({ text: "", error: false });

  /**
   * Upload a manual through the existing API.
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    setMessage({ text: "Handbuch wird hochgeladen...", error: false });
    try {
      await uploadMachineManual(formData);
      form.reset();
      await onUploaded();
      setMessage({ text: "Handbuch hochgeladen.", error: false });
    } catch (error) {
      setMessage({ text: documentErrorMessage(error), error: true });
    }
  }

  return (
    <article className="card app-card lg:order-4 lg:col-span-12">
      <form onSubmit={handleSubmit}>
        <div className="card-body">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Maschinenhandbuch hochladen</h2>
              <p className="panel-meta">PDF, TXT oder HTML sicher speichern und analysieren</p>
            </div>
            <span className="badge badge-ai">Handbuch</span>
          </div>
          <div className="status-explainer">
            <p><strong>Handbuch hochladen:</strong> Ordne die Datei möglichst einer Maschine und einem Bereich zu, damit Suche und Berechtigungen präzise bleiben.</p>
          </div>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="manual-file">Datei</label>
              <input className="input input-bordered" id="manual-file" name="file" type="file" accept=".pdf,.txt,.html,.htm,application/pdf,text/plain,text/html" />
            </div>
            <div className="field">
              <label htmlFor="manual-machine">Maschine</label>
              <select className="select select-bordered" id="manual-machine" name="machine_id">
                <option value="">Keine Maschine</option>
                {machines.map((machine) => <option key={machine.id} value={machine.id}>{machine.name}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="manual-department">Bereich</label>
              <input className="input input-bordered" id="manual-department" name="department" />
            </div>
          </div>
          <div className="toolbar form-actions">
            <button className="btn btn-primary" type="submit">Handbuch hochladen</button>
            <span className={`panel-meta${message.error ? " is-error" : ""}`}>{message.text}</span>
          </div>
        </div>
      </form>
    </article>
  );
}

/**
 * Render the document review panel.
 */
export function ReviewPanel({ review }: ReviewPanelProps): ReactNode {
  const findings = review?.findings || review?.checks || [];
  const recommendations = review?.recommendations || [];
  const documentMeta = review?.document || {};
  const status = reviewStatusText(review?.status);

  return (
    <article className="card app-card lg:order-2 lg:col-span-12" hidden={!review}>
      <div className="card-body">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Dokumentprüfung</h2>
            <p className="panel-meta">Prüfung für {documentMeta.title || documentMeta.filename || "Dokument"}</p>
          </div>
          <span className={statusBadgeClass(review?.status)}>{status}</span>
        </div>
        <div className="review-score-card">
          <ReviewMetric label="Qualitätsscore" value={String(review?.quality_score || 0)} />
          <ReviewMetric label="Status" value={status} />
          <ReviewMetric label="Quelle" value={documentMeta.source || documentMeta.document_type || "Dokument"} />
        </div>
        <div className="review-checklist">
          {findings.length ? findings.map((finding, index) => <ReviewFindingItem finding={finding} key={`${finding.field || "finding"}-${index}`} />) : <ReviewFindingItem finding={{ field: "Keine Findings", message: "Die Prüfung hat keine offenen Punkte gefunden.", severity: "good" }} />}
        </div>
        <div className="panel-meta">{recommendations.length ? `Empfehlungen: ${recommendations.join(" | ")}` : "Keine Empfehlungen erforderlich."}</div>
      </div>
    </article>
  );
}

/**
 * Render a summary or analysis panel.
 */
export function SummaryPanel({ summary }: SummaryPanelProps): ReactNode {
  return (
    <article className="card app-card lg:order-2 lg:col-span-12" hidden={!summary}>
      <div className="card-body">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Zusammenfassung</h2>
            <p className="panel-meta">{summary?.title || "Dokument zusammenfassen"}</p>
          </div>
          <span className="badge badge-status is-open">{summary?.summary_status || summary?.analysis_status || "-"}</span>
        </div>
        <pre className="panel-meta whitespace-pre-wrap">{summary?.summary || summary?.analysis || "Keine Zusammenfassung vorhanden."}</pre>
      </div>
    </article>
  );
}

/**
 * Render one review metric.
 */
function ReviewMetric({ label, value }: { readonly label: string; readonly value: string }): ReactNode {
  return (
    <div>
      <span className="resource-label">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

/**
 * Render one review finding.
 */
function ReviewFindingItem({ finding }: { readonly finding: ReviewFinding }): ReactNode {
  const severity = String(finding.severity || "").toLowerCase();
  const tone = ["critical", "error", "high"].includes(severity) ? "is-critical" : ["warning", "warn", "medium", "needs_review"].includes(severity) ? "is-warning" : "is-good";
  const marker = tone === "is-critical" ? "!" : tone === "is-warning" ? "?" : "OK";

  return (
    <article className={`review-check-item ${tone}`}>
      <span className="review-check-marker">{marker}</span>
      <div className="review-check-content">
        <strong>{finding.field || "Prüfpunkt"}</strong>
        <span>{finding.message || "Keine Details vorhanden."}</span>
        <small>{finding.severity ? `Schweregrad: ${finding.severity}` : "Hinweis"}</small>
      </div>
    </article>
  );
}
