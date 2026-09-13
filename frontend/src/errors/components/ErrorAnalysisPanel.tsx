import { useState, type FormEvent, type ReactNode } from "react";

import { analyzeErrorDescription, loadErrorAssistantContext, loadSimilarErrors } from "../errorApi";
import type {
  ErrorAssistantResult,
  ErrorDraft,
  MessageState,
  SimilarErrorResult
} from "../errorTypes";
import { draftFromAnalysis, errorMessage } from "../errorUtils";

type ErrorAnalysisPanelProps = {
  readonly currentDepartment: string;
  readonly drawerMode?: boolean;
  readonly hidden: boolean;
  readonly onApplyDraft: (draft: ErrorDraft) => void;
  readonly onSimilarResult: (result: SimilarErrorResult) => void;
};

/**
 * Return a string value from an assistant action preview payload.
 */
function previewValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/**
 * Render an assistant source list.
 */
function SourcePanel({ result }: { readonly result: ErrorAssistantResult | null }): ReactNode {
  const sources = result?.sources || [];
  return (
    <div className="rag-source-panel" hidden={!sources.length}>
      {sources.map((source, index) => (
        <article className="source-card" key={`${source.title || "Quelle"}-${index}`}>
          <strong>{source.title || "Quelle"}</strong>
          <span>{source.source_type || "Wissensquelle"}</span>
          {source.url ? <a href={source.url}>Öffnen</a> : null}
        </article>
      ))}
    </div>
  );
}

/**
 * Render a compact AI action preview.
 */
function ActionPreview({ result }: { readonly result: ErrorAssistantResult | null }): ReactNode {
  const preview = result?.action_preview;
  return (
    <div className="ai-action-preview" hidden={!preview}>
      {preview ? (
        <>
          <strong>{preview.label || "AI-Aktion"}</strong>
          <p>{previewValue(preview.payload?.title) || previewValue(preview.payload?.description) || "Vorschlag vorbereitet."}</p>
        </>
      ) : null}
    </div>
  );
}

/**
 * Render the free-text error analysis panel.
 */
export function ErrorAnalysisPanel({ currentDepartment, drawerMode = false, hidden, onApplyDraft, onSimilarResult }: ErrorAnalysisPanelProps): ReactNode {
  const [analysis, setAnalysis] = useState<Partial<ErrorDraft> | null>(null);
  const [assistantResult, setAssistantResult] = useState<ErrorAssistantResult | null>(null);
  const [description, setDescription] = useState("");
  const [message, setMessage] = useState<MessageState>({ text: "", error: false });

  /**
   * Generate an analysis and similar-error context.
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setMessage({ text: "AI analysiert...", error: false });
    try {
      const nextAnalysis = await analyzeErrorDescription(description);
      setAnalysis(nextAnalysis);
      setMessage({ text: "Analyse erstellt.", error: false });
      onSimilarResult(await loadSimilarErrors(description, nextAnalysis.machine || ""));
      try {
        const context = await loadErrorAssistantContext(description);
        setAssistantResult(context);
        if (context.diagnostics?.rag_source_count) {
          setMessage({ text: `Analyse erstellt. ${context.diagnostics.rag_source_count} Quellen gefunden.`, error: false });
        }
      } catch (error) {
        setAssistantResult(null);
        setMessage({ text: `Analyse erstellt. Quellenkontext nicht verfügbar: ${errorMessage(error)}`, error: false });
      }
    } catch (error) {
      setMessage({ text: errorMessage(error), error: true });
    }
  }

  /**
   * Copy the generated analysis into the create form.
   */
  function applyAnalysis(): void {
    if (!analysis) return;
    onApplyDraft(draftFromAnalysis(analysis, currentDepartment));
  }

  return (
    <details className="incident-action-panel app-card" hidden={hidden} open={drawerMode}>
      <summary>
        <span>
          <strong>Aus Beschreibung vorschlagen</strong>
          <small>Freitext in prüfbare Ursache, Lösung und Katalogdaten umwandeln</small>
        </span>
      </summary>
      <div className="incident-form-body">
        <form onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="error-analysis-description">Fehlerbeschreibung</label>
            <textarea className="textarea textarea-bordered" id="error-analysis-description" name="description" placeholder="z. B. Sensor meldet sporadisch kein Signal an Maschine 3." value={description} onChange={(event) => setDescription(event.currentTarget.value)} />
          </div>
          <div className="toolbar form-actions">
            <button className="btn btn-primary" type="submit">Vorschlag erstellen</button>
            <span className={`panel-meta${message.error ? " is-error" : ""}`} role="status" aria-live="polite">{message.text}</span>
          </div>
        </form>
        <div className="suggestion-box incident-suggestion-box" hidden={!analysis}>
          <div className="form-grid">
            {(["machine", "department", "title", "symptoms", "possible_causes", "solution"] as const).map((field) => (
              <div className={`field${field === "title" || field === "symptoms" ? " is-full" : ""}`} key={field}>
                <label htmlFor={`analysis-${field}`}>{analysisLabel(field)}</label>
                {field === "symptoms" || field === "possible_causes" || field === "solution" ? (
                  <textarea className="textarea textarea-bordered" id={`analysis-${field}`} value={analysis?.[field] || ""} onChange={(event) => setAnalysis({ ...analysis, [field]: event.currentTarget.value })} />
                ) : (
                  <input className="input input-bordered" id={`analysis-${field}`} value={analysis?.[field] || ""} onChange={(event) => setAnalysis({ ...analysis, [field]: event.currentTarget.value })} />
                )}
              </div>
            ))}
          </div>
          <ActionPreview result={assistantResult} />
          <SourcePanel result={assistantResult} />
          <div className="toolbar form-actions">
            <button className="btn btn-primary" type="button" onClick={applyAnalysis}>In Störungsformular übernehmen</button>
          </div>
        </div>
      </div>
    </details>
  );
}

/**
 * Return the form label for one analysis field.
 */
function analysisLabel(field: keyof ErrorDraft): string {
  const labels: Partial<Record<keyof ErrorDraft, string>> = {
    machine: "Maschine",
    department: "Bereich",
    title: "Fehler",
    symptoms: "Symptome",
    possible_causes: "Mögliche Ursachen",
    solution: "Lösung"
  };
  return labels[field] || field;
}
