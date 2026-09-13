import { useEffect, useRef, useState, type ReactNode } from "react";

import { MACHINE_STATUS_OPTIONS, PRODUCTION_STATUS_OPTIONS } from "../handoverOptions";
import type { HandoverMessage, HandoverPayload, HandoverRecord } from "../handoverTypes";

type DialogTextArea = {
  readonly className?: string;
  readonly field: keyof HandoverPayload;
  readonly id: string;
  readonly label: string;
  readonly rows: number;
};

type HandoverDialogProps = {
  readonly handover: HandoverRecord | null;
  readonly message: HandoverMessage;
  readonly onClose: () => void;
  readonly onSave: (id: number, payload: HandoverPayload) => void;
  readonly saving: boolean;
};

const DIALOG_TEXT_AREAS: readonly DialogTextArea[] = [
  {
    id: "dlg-ho-content",
    field: "content",
    label: "Status der aktuellen Schicht",
    rows: 3,
    className: "field is-full",
  },
  { id: "dlg-ho-open", field: "open_tasks", label: "Offene Tasks", rows: 2 },
  { id: "dlg-ho-machine", field: "machine_notes", label: "Maschinenstatus / Auffälligkeiten", rows: 2 },
  { id: "dlg-ho-cause", field: "cause", label: "Ursache", rows: 2 },
  { id: "dlg-ho-action", field: "action_taken", label: "Maßnahme", rows: 2 },
  { id: "dlg-ho-safety", field: "safety_notes", label: "Sicherheit", rows: 2 },
  { id: "dlg-ho-material", field: "material_notes", label: "Material / Ersatzteile", rows: 2 },
  {
    id: "dlg-ho-next",
    field: "next_notes",
    label: "Hinweise für nächste Schicht",
    rows: 2,
    className: "field is-full",
  },
];

/**
 * Return the editable dialog payload for one handover record.
 */
function payloadFromHandover(handover: HandoverRecord | null): HandoverPayload {
  return {
    production_status: handover?.production_status || "",
    machine_status: handover?.machine_status || "",
    content: handover?.content || "",
    open_tasks: handover?.open_tasks || "",
    machine_notes: handover?.machine_notes || "",
    cause: handover?.cause || "",
    action_taken: handover?.action_taken || "",
    safety_notes: handover?.safety_notes || "",
    material_notes: handover?.material_notes || "",
    next_notes: handover?.next_notes || "",
  };
}

/**
 * Render one dialog text area field.
 */
function DialogTextAreaField({
  field,
  formState,
  onChange,
  className = "field",
  id,
  label,
  rows,
}: DialogTextArea & {
  readonly formState: HandoverPayload;
  readonly onChange: (field: keyof HandoverPayload, value: string) => void;
}): ReactNode {
  return (
    <div className={className}>
      <label htmlFor={id}>{label}</label>
      <textarea
        className="textarea textarea-bordered"
        id={id}
        rows={rows}
        value={String(formState[field] || "")}
        onChange={(event) => onChange(field, event.currentTarget.value)}
      />
    </div>
  );
}

/**
 * Render the edit dialog for open handovers.
 */
export function HandoverDialog({ handover, message, onClose, onSave, saving }: HandoverDialogProps): ReactNode {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [formState, setFormState] = useState<HandoverPayload>(() => payloadFromHandover(handover));

  /**
   * Update one dialog field.
   */
  function updateField(field: keyof HandoverPayload, value: string): void {
    setFormState((current) => ({ ...current, [field]: value }));
  }

  /**
   * Close the dialog and notify the parent.
   */
  function closeDialog(): void {
    dialogRef.current?.close();
    onClose();
  }

  /**
   * Submit the dialog update to the parent.
   */
  function saveDialog(): void {
    if (!handover) return;
    onSave(handover.id, formState);
  }

  useEffect(() => {
    setFormState(payloadFromHandover(handover));
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (handover && !dialog.open) {
      dialog.showModal();
      return;
    }
    if (!handover && dialog.open) {
      dialog.close();
    }
  }, [handover]);

  return (
    <dialog className="handover-dialog" id="ho-dialog" aria-modal="true" aria-labelledby="ho-dlg-title" ref={dialogRef}>
      <form className="handover-dialog-card app-card" method="dialog">
        <header className="panel-header">
          <div>
            <h3 className="panel-title" id="ho-dlg-title">
              Übergabe bearbeiten
            </h3>
            <p className="panel-meta">Nur offene Übergaben können aktualisiert werden.</p>
          </div>
          <button className="btn btn-ghost btn-sm" id="dlg-ho-cancel" type="button" onClick={closeDialog}>
            Schließen
          </button>
        </header>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="dlg-ho-production">Produktionsstatus</label>
            <select
              className="select select-bordered"
              id="dlg-ho-production"
              value={String(formState.production_status || "")}
              onChange={(event) => updateField("production_status", event.currentTarget.value)}
            >
              <option value="">Nicht bewertet</option>
              {PRODUCTION_STATUS_OPTIONS.map((status) => (
                <option key={status.value} value={status.value}>
                  {status.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="dlg-ho-machine-status">Maschinenstatus</label>
            <select
              className="select select-bordered"
              id="dlg-ho-machine-status"
              value={String(formState.machine_status || "")}
              onChange={(event) => updateField("machine_status", event.currentTarget.value)}
            >
              <option value="">Nicht bewertet</option>
              {MACHINE_STATUS_OPTIONS.map((status) => (
                <option key={status.value} value={status.value}>
                  {status.label}
                </option>
              ))}
            </select>
          </div>
          {DIALOG_TEXT_AREAS.map((field) => (
            <DialogTextAreaField
              formState={formState}
              key={field.id}
              onChange={updateField}
              {...field}
            />
          ))}
        </div>
        <div className="toolbar form-actions">
          <button className="btn btn-primary btn-sm" id="dlg-ho-save" type="button" disabled={saving} onClick={saveDialog}>
            {saving ? "Speichert..." : "Speichern"}
          </button>
          <span className={`panel-meta${message.isError ? " is-error" : ""}`} id="dlg-ho-msg" role="status" aria-live="polite">
            {message.text}
          </span>
        </div>
      </form>
    </dialog>
  );
}
