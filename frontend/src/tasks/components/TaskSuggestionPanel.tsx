import {
  useState,
  type FormEvent,
  type ReactNode
} from "react";

import { suggestTask } from "../taskApi";
import type { TaskSuggestion } from "../taskTypes";
import {
  draftFromSuggestion,
  normalizeSuggestion,
  taskErrorMessage
} from "../taskUtils";

type TaskSuggestionPanelProps = {
  readonly hidden: boolean;
  readonly onApplySuggestion: (suggestion: ReturnType<typeof draftFromSuggestion>) => void;
};

/**
 * Render the AI task suggestion panel.
 */
export function TaskSuggestionPanel({ hidden, onApplySuggestion }: TaskSuggestionPanelProps): ReactNode {
  const [text, setText] = useState("");
  const [suggestion, setSuggestion] = useState<TaskSuggestion | null>(null);
  const [message, setMessage] = useState({ text: "", error: false });
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(() => (
    typeof window.matchMedia === "function"
      ? !window.matchMedia("(max-width: 639px)").matches
      : true
  ));

  /**
   * Update one editable suggestion field.
   */
  function updateSuggestion(fieldName: keyof TaskSuggestion, value: string): void {
    if (!suggestion) return;
    setSuggestion({ ...suggestion, [fieldName]: value });
  }

  /**
   * Request one AI-generated task suggestion.
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setMessage({ text: "AI erstellt Vorschlag...", error: false });

    try {
      const payload = await suggestTask(text);
      setSuggestion(normalizeSuggestion(payload));
      setMessage({ text: "Vorschlag erstellt.", error: false });
    } catch (error) {
      setMessage({ text: taskErrorMessage(error), error: true });
    } finally {
      setBusy(false);
    }
  }

  /**
   * Apply the editable suggestion to the main task form.
   */
  function handleApply(): void {
    if (!suggestion) return;
    onApplySuggestion(draftFromSuggestion(suggestion));
  }

  return (
    <details
      className="task-action-panel app-card"
     
     
     
      hidden={hidden}
      onToggle={(event) => setOpen(event.currentTarget.open)}
      open={open}
    >
      <summary>
        <span>
          <strong>Aus Meldung erstellen</strong>
          <small>Freitext in eine bearbeitbare Aufgabe umwandeln</small>
        </span>
      </summary>
      <div className="task-form-body">
        <form onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="react-task-suggest-text">Beschreibung</label>
            <textarea
              className="textarea textarea-bordered"
              disabled={busy}
              id="react-task-suggest-text"
              name="text"
              onChange={(event) => setText(event.target.value)}
              placeholder="z. B. Presse 3 macht laute Geräusche am Lager."
              value={text}
            />
          </div>
          <div className="toolbar form-actions">
            <button className="btn btn-primary" disabled={busy} type="submit">
              {busy ? "Erstellt..." : "Vorschlag erstellen"}
            </button>
            <span
              className={`panel-meta${message.error ? " is-error" : ""}`}
              role="status"
              aria-live="polite"
            >
              {message.text}
            </span>
          </div>
        </form>
        <div className="suggestion-box task-suggestion-box" hidden={!suggestion}>
          {suggestion ? (
            <>
              <div className="form-grid">
                <div className="field">
                  <label htmlFor="react-suggest-title">Titel</label>
                  <input className="input input-bordered" id="react-suggest-title" onChange={(event) => updateSuggestion("title", event.target.value)} value={suggestion.title} />
                </div>
                <div className="field">
                  <label htmlFor="react-suggest-department">Bereich</label>
                  <input className="input input-bordered" id="react-suggest-department" onChange={(event) => updateSuggestion("department", event.target.value)} value={suggestion.department} />
                </div>
                <div className="field">
                  <label htmlFor="react-suggest-priority">Priorität</label>
                  <select className="select select-bordered" id="react-suggest-priority" onChange={(event) => updateSuggestion("priority", event.target.value)} value={suggestion.priority}>
                    <option value="urgent">Kritisch</option>
                    <option value="soon">Bald</option>
                    <option value="normal">Normal</option>
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="react-suggest-status">Status</label>
                  <select className="select select-bordered" id="react-suggest-status" onChange={(event) => updateSuggestion("status", event.target.value)} value={suggestion.status}>
                    <option value="open">Offen</option>
                    <option value="in_progress">In Arbeit</option>
                    <option value="done">Erledigt</option>
                    <option value="cancelled">Abgebrochen</option>
                  </select>
                </div>
                <div className="field is-full">
                  <label htmlFor="react-suggest-description">Beschreibung</label>
                  <textarea className="textarea textarea-bordered" id="react-suggest-description" onChange={(event) => updateSuggestion("description", event.target.value)} value={suggestion.description} />
                </div>
                <div className="field">
                  <label htmlFor="react-suggest-cause">Mögliche Ursache</label>
                  <textarea className="textarea textarea-bordered" id="react-suggest-cause" onChange={(event) => updateSuggestion("possible_cause", event.target.value)} value={suggestion.possible_cause || ""} />
                </div>
                <div className="field">
                  <label htmlFor="react-suggest-action">Nächste Aktion</label>
                  <textarea className="textarea textarea-bordered" id="react-suggest-action" onChange={(event) => updateSuggestion("recommended_action", event.target.value)} value={suggestion.recommended_action || ""} />
                </div>
              </div>
              <div className="toolbar form-actions">
                <button className="btn btn-primary" onClick={handleApply} type="button">
                  In Aufgabenformular übernehmen
                </button>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </details>
  );
}
