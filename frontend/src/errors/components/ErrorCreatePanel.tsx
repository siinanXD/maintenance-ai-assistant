import type { FormEvent, ReactNode } from "react";

import { createErrorEntry, loadSimilarErrors } from "../errorApi";
import type { Department, ErrorDraft, MessageState, SimilarErrorResult } from "../errorTypes";
import { createEmptyErrorDraft, errorMessage } from "../errorUtils";
import { ErrorFormFields } from "./ErrorFormFields";

type ErrorCreatePanelProps = {
  readonly departments: readonly Department[];
  readonly draft: ErrorDraft;
  readonly drawerMode?: boolean;
  readonly hidden: boolean;
  readonly message: MessageState;
  readonly onDraftChange: (draft: ErrorDraft) => void;
  readonly onMessageChange: (message: MessageState) => void;
  readonly onSaved: () => Promise<void>;
  readonly onSimilarResult: (result: SimilarErrorResult) => void;
};

/**
 * Render the error creation form.
 */
export function ErrorCreatePanel(props: ErrorCreatePanelProps): ReactNode {
  /**
   * Save a new error and refresh catalog data.
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    props.onMessageChange({ text: "Fehler wird geprüft...", error: false });
    try {
      props.onSimilarResult(await loadSimilarErrors(props.draft.symptoms || props.draft.title, props.draft.machine));
      await createErrorEntry(props.draft);
      props.onDraftChange(createEmptyErrorDraft());
      await props.onSaved();
      props.onMessageChange({ text: "Fehler gespeichert.", error: false });
    } catch (error) {
      props.onMessageChange({ text: errorMessage(error), error: true });
    }
  }

  return (
    <details
      className="incident-action-panel app-card"
     
     
     
      hidden={props.hidden}
      id="incident-create"
      open={props.drawerMode}
    >
      <summary>
        <span>
          <strong>Störung erfassen</strong>
          <small>Maschine, Kategorie, Symptome, Ursache, Lösung und Auswirkungen speichern</small>
        </span>
      </summary>
      <form onSubmit={handleSubmit}>
        <div className="incident-form-body">
          <ErrorFormFields departments={props.departments} draft={props.draft} idPrefix="error" onDraftChange={props.onDraftChange} />
          <div className="toolbar form-actions">
            <button className="btn btn-primary" type="submit">Störung speichern</button>
            <span className={`panel-meta${props.message.error ? " is-error" : ""}`} role="status" aria-live="polite">{props.message.text}</span>
          </div>
        </div>
      </form>
    </details>
  );
}
