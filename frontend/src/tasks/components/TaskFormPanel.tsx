import {
  useEffect,
  useState,
  type FormEvent,
  type ReactNode
} from "react";

import { saveTask } from "../taskApi";
import type { Department, MessageState, TaskDraft } from "../taskTypes";
import { createEmptyTaskDraft, taskErrorMessage } from "../taskUtils";

type TaskFormPanelProps = {
  readonly departments: readonly Department[];
  readonly draft: TaskDraft;
  readonly drawerMode?: boolean;
  readonly editingTaskId: number | null;
  readonly hidden: boolean;
  readonly message: MessageState;
  readonly onCancelEdit: () => void;
  readonly onDraftChange: (draft: TaskDraft) => void;
  readonly onMessageChange: (message: MessageState) => void;
  readonly onSaved: () => Promise<void>;
};

/**
 * Render the create and edit task form.
 */
export function TaskFormPanel({
  departments,
  draft,
  drawerMode = false,
  editingTaskId,
  hidden,
  message,
  onCancelEdit,
  onDraftChange,
  onMessageChange,
  onSaved
}: TaskFormPanelProps): ReactNode {
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(() => (
    drawerMode || typeof window.matchMedia !== "function"
      ? true
      : !window.matchMedia("(max-width: 639px)").matches
  ));

  /**
   * Keep the form open when it is rendered inside the action drawer.
   */
  useEffect(() => {
    if (drawerMode) {
      setOpen(true);
    }
  }, [drawerMode]);

  /**
   * Open the form when edit mode becomes active.
   */
  useEffect(() => {
    if (editingTaskId) {
      setOpen(true);
    }
  }, [editingTaskId]);

  /**
   * Update the local disclosure state unless the drawer owns visibility.
   */
  function handleToggle(openState: boolean): void {
    if (!drawerMode) {
      setOpen(openState);
    }
  }

  /**
   * Update one controlled task field.
   */
  function updateField(fieldName: keyof TaskDraft, value: string): void {
    onDraftChange({ ...draft, [fieldName]: value });
  }

  /**
   * Persist the current task form.
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setBusy(true);
    onMessageChange({
      text: editingTaskId ? "Aufgabe wird aktualisiert..." : "Aufgabe wird gespeichert...",
      error: false
    });

    try {
      await saveTask(draft, editingTaskId);
      onDraftChange(createEmptyTaskDraft());
      await onSaved();
      onMessageChange({
        text: editingTaskId ? "Aufgabe aktualisiert." : "Aufgabe gespeichert.",
        error: false
      });
    } catch (error) {
      onMessageChange({ text: taskErrorMessage(error), error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <details
      className={`task-action-panel app-card${drawerMode ? " is-drawer-panel" : ""}`}
      data-default-collapsed="true"
      data-mobile-collapsible
      data-permission-write="tasks"
      hidden={hidden}
      id="task-create"
      onToggle={(event) => handleToggle(event.currentTarget.open)}
      open={open}
    >
      <summary>
        <span>
          <strong>Aufgabe anlegen</strong>
          <small>Bereich, Priorität, Status und Fälligkeit setzen</small>
        </span>
      </summary>
      <form data-task-form onSubmit={handleSubmit}>
        <div className="task-form-body">
          <div className="form-grid">
            <div className="field">
              <label htmlFor="react-task-department">Bereich</label>
              <select
                className="select select-bordered"
                disabled={busy}
                id="react-task-department"
                name="department"
                onChange={(event) => updateField("department", event.target.value)}
                value={draft.department}
              >
                <option value="">Bereich wählen</option>
                {departments.map((department) => (
                  <option key={department.id ?? department.name} value={department.name}>{department.name}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="react-task-title">Überschrift</label>
              <input
                className="input input-bordered"
                disabled={busy}
                id="react-task-title"
                name="title"
                onChange={(event) => updateField("title", event.target.value)}
                required
                value={draft.title}
              />
            </div>
            <div className="field">
              <label htmlFor="react-task-priority">Priorität</label>
              <select
                className="select select-bordered"
                disabled={busy}
                id="react-task-priority"
                name="priority"
                onChange={(event) => updateField("priority", event.target.value)}
                value={draft.priority}
              >
                <option value="urgent">Kritisch</option>
                <option value="soon">Bald</option>
                <option value="normal">Normal</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="react-task-status">Status</label>
              <select
                className="select select-bordered"
                disabled={busy}
                id="react-task-status"
                name="status"
                onChange={(event) => updateField("status", event.target.value)}
                value={draft.status}
              >
                <option value="open">Offen</option>
                <option value="in_progress">In Arbeit</option>
                <option value="done">Erledigt</option>
                <option value="cancelled">Abgebrochen</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="react-task-due-date">Fällig am</label>
              <input
                className="input input-bordered"
                disabled={busy}
                id="react-task-due-date"
                name="due_date"
                onChange={(event) => updateField("due_date", event.target.value)}
                type="date"
                value={draft.due_date}
              />
            </div>
            <div className="field is-full">
              <label htmlFor="react-task-description">Beschreibung</label>
              <textarea
                className="textarea textarea-bordered"
                disabled={busy}
                id="react-task-description"
                name="description"
                onChange={(event) => updateField("description", event.target.value)}
                placeholder="Maschine, Beobachtung, Zielzustand und erste Prüfschritte"
                value={draft.description}
              />
            </div>
          </div>
          <div className="toolbar form-actions">
            <button className="btn btn-primary" data-task-submit-button disabled={busy} type="submit">
              {busy ? (editingTaskId ? "Aktualisiert..." : "Speichert...") : (editingTaskId ? "Aufgabe aktualisieren" : "Aufgabe speichern")}
            </button>
            <button
              className="btn btn-ghost"
              data-task-edit-cancel
              hidden={!editingTaskId}
              onClick={onCancelEdit}
              type="button"
            >
              Bearbeiten abbrechen
            </button>
            <span
              className={`panel-meta${message.error ? " is-error" : ""}`}
              data-task-message
              role="status"
              aria-live="polite"
            >
              {message.text}
            </span>
          </div>
        </div>
      </form>
    </details>
  );
}
