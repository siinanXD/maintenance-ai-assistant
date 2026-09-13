import { type FormEvent, type ReactNode } from "react";

import {
  EMPTY_ADMIN_AI_SOURCE_CHECK_STATE,
  type AdminAiSourceCheckState,
  type AdminAiSourceTestSource
} from "../adminAiSourceCheckModel";

type AdminAiSourceCheckProps = {
  readonly onCreateFaq: () => void;
  readonly onFeedback: (rating: string, comment?: string) => void;
  readonly onReset: () => void;
  readonly onSourceTestSubmit: (form: HTMLFormElement, intent?: string) => void;
  readonly sourceCheckState: AdminAiSourceCheckState;
};

type AdminAiSourceTestPanelProps = Partial<AdminAiSourceCheckProps> & {
  readonly layout?: "default" | "arena";
};

/**
 * Return the submit button value that triggered a source test form submit.
 */
function sourceTestSubmitIntent(event: FormEvent<HTMLFormElement>): string | undefined {
  const nativeEvent = event.nativeEvent as SubmitEvent;
  const submitter = nativeEvent.submitter;

  return submitter instanceof HTMLButtonElement && submitter.value ? submitter.value : undefined;
}

/**
 * Render the shared source test form and result panel.
 */
export function AdminAiSourceTestPanel({
  layout = "default",
  onCreateFaq = () => {},
  onFeedback = () => {},
  onReset = () => {},
  onSourceTestSubmit = () => {},
  sourceCheckState = EMPTY_ADMIN_AI_SOURCE_CHECK_STATE
}: AdminAiSourceTestPanelProps): ReactNode {
  const isArenaLayout = layout === "arena";
  const formClassName = isArenaLayout ? "stack source-test-form source-test-form-card" : "panel stack source-test-form";
  const resultClassName = isArenaLayout ? "source-test-result source-test-result-card" : "panel source-test-result";

  return (
    <>
      <div className={`source-test-layout${isArenaLayout ? " is-arena" : ""}`}>
        <form
          className={formClassName}
          onSubmit={(event) => {
            event.preventDefault();
            onSourceTestSubmit(event.currentTarget, sourceTestSubmitIntent(event));
          }}
        >
          <div className="form-grid">
            <label>
              <span>Workflow</span>
              <select className="input input-bordered" name="workflow" aria-label="Workflow">
                <option value="chat">Wartungs-Chat</option>
                <option value="general_chat">Allgemeiner Chat</option>
                <option value="error_analysis">Fehleranalyse</option>
                <option value="task_suggestion">Aufgaben-Vorschlag</option>
                <option value="document_review">Dokument-Prüfung</option>
              </select>
            </label>
            <label>
              <span>Modus</span>
              <select className="input input-bordered" name="mode" aria-label="Testmodus">
                <option value="dry">Dry-run ohne Modellkosten</option>
                <option value="live">Live-Test mit echtem AI-Call</option>
              </select>
            </label>
          </div>
          <label>
            <span>Testfrage</span>
            <textarea
              className="input input-bordered"
              name="question"
              placeholder="z. B. Warum fällt Presse 3 bei Hydraulikdruck ab?"
              rows={isArenaLayout ? 3 : 5}
            />
          </label>
          {isArenaLayout ? null : (
            <label>
              <span>Optionaler Kontext</span>
              <textarea
                className="input input-bordered"
                name="context"
                placeholder="Maschine, Abteilung, Fehlercode oder bekannte Quelle"
                rows={4}
              />
            </label>
          )}
          <div className={`toolbar${isArenaLayout ? " source-test-toolbar-arena" : ""}`}>
            <button
              className="btn btn-secondary"
              disabled={sourceCheckState.isRunning}
              type="submit"
              name="intent"
              value="dry"
            >
              {sourceCheckState.isRunning ? "Lädt..." : "Dry-run anzeigen"}
            </button>
            <button
              className="btn btn-primary"
              disabled={sourceCheckState.isRunning}
              type="submit"
              name="intent"
              value="live"
            >
              {sourceCheckState.isRunning ? "Lädt..." : "Live-Test starten"}
            </button>
            <button className="btn btn-ghost" type="button" onClick={onReset}>
              Arena zurücksetzen
            </button>
          </div>
        </form>

        <section className={resultClassName}>
          <div className="panel-header source-test-result-header">
            <div>
              <h3>{isArenaLayout ? "Antwort" : "Antwort & Quellen"}</h3>
              <p className="panel-meta">{sourceCheckState.testMeta}</p>
            </div>
            <span className={sourceCheckState.stateClassName}>
              {sourceCheckState.stateLabel}
            </span>
          </div>
          <div className="source-test-answer">
            {sourceCheckState.answerText}
          </div>
          <div className="source-test-score-grid">
            <article>
              <span>Quellen</span>
              <strong>{sourceCheckState.kpis.sources}</strong>
            </article>
            <article>
              <span>Sicherheit</span>
              <strong>
                {sourceCheckState.kpis.confidence}
              </strong>
            </article>
            <article>
              <span>Kosten</span>
              <strong>{sourceCheckState.kpis.cost}</strong>
            </article>
            <article>
              <span>Latenz</span>
              <strong>{sourceCheckState.kpis.latency}</strong>
            </article>
          </div>
          <SourceCheckSources
            reportedSourceCount={sourceCheckState.reportedSourceCount}
            sources={sourceCheckState.sources}
          />
          <div
            className="toolbar source-test-actions"
            hidden={!sourceCheckState.actionsVisible}
          >
            <button
              className="btn btn-primary"
              disabled={sourceCheckState.isSaving}
              type="button"
              onClick={() => {
                onFeedback("helpful");
              }}
            >
              Gut
            </button>
            <button
              className="btn btn-secondary"
              disabled={sourceCheckState.isSaving}
              type="button"
              onClick={() => {
                onFeedback("partially_helpful");
              }}
            >
              Teilweise
            </button>
            <button
              className="btn btn-ghost"
              disabled={sourceCheckState.isSaving}
              type="button"
              onClick={() => {
                onFeedback("not_helpful");
              }}
            >
              Schlecht
            </button>
            <button
              className="btn btn-secondary"
              disabled={sourceCheckState.isSaving}
              type="button"
              onClick={onCreateFaq}
            >
              FAQ daraus erstellen
            </button>
            <button
              className="btn btn-ghost"
              disabled={sourceCheckState.isSaving}
              type="button"
              onClick={() => {
                onFeedback("not_helpful", "Quelle fehlt laut KI-Admin Quellenprüfung");
              }}
            >
              Quelle fehlt
            </button>
          </div>
          {sourceCheckState.errorMessage ? (
            <p className="panel-meta text-error">{sourceCheckState.errorMessage}</p>
          ) : null}
        </section>
      </div>

      <section className="panel mt-4">
          <div className="panel-header">
            <h3>Prompt-Vorschau</h3>
            <span className="panel-meta">{sourceCheckState.promptMeta}</span>
          </div>
          <pre className="ai-debug-prompt">{sourceCheckState.promptPreview}</pre>
        </section>
    </>
  );
}

/**
 * Render source cards or the empty source row for the Source Check result.
 */
function SourceCheckSources({
  reportedSourceCount,
  sources
}: {
  readonly reportedSourceCount: number;
  readonly sources: readonly AdminAiSourceTestSource[];
}): ReactNode {
  const hiddenSourceCount = Math.max(reportedSourceCount - sources.length, 0);

  return (
    <div className="source-test-sources">
      {sources.length ? (
        sources.map((source, index) => (
          <article className="source-test-source" key={`${source.title}-${index}`}>
            <strong>{source.title}</strong>
            <small>{source.meta}</small>
          </article>
        ))
      ) : (
        <div className="stat-row">
          <span>Quellen</span>
          <strong>
            {hiddenSourceCount
              ? `${hiddenSourceCount} Quellen referenziert, aber in dieser Ansicht nicht sichtbar.`
              : "Keine Quellen gefunden."}
          </strong>
        </div>
      )}
      {sources.length && hiddenSourceCount ? (
        <div className="stat-row">
          <span>Hinweis</span>
          <strong>{hiddenSourceCount} weitere Quellen sind nur als Metadaten vorhanden.</strong>
        </div>
      ) : null}
    </div>
  );
}

/**
 * Render the source check Admin-AI page.
 */
export function AdminAiSourceCheck(props: AdminAiSourceCheckProps): ReactNode {
  return (
    <section className="ai-admin-area source-check-area" id="ai-source-check">
      <AdminAiSourceTestPanel {...props} layout="default" />
    </section>
  );
}
