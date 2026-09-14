import { useEffect, useRef, useState, type ReactNode } from "react";

import type { ShiftplanEditDraft, ShiftplanEntry, ShiftplansMessage } from "../shiftplanTypes";
import { SHIFT_WINDOWS } from "../shiftplanUtils";

type ShiftOption = {
  readonly label: string;
  readonly value: string;
};

type ShiftplansEditDialogProps = {
  readonly deleting: boolean;
  readonly entry: ShiftplanEntry | null;
  readonly isAdmin: boolean;
  readonly message: ShiftplansMessage;
  readonly onClose: () => void;
  readonly onDelete: (entry: ShiftplanEntry) => void;
  readonly onSave: (entry: ShiftplanEntry, draft: ShiftplanEditDraft) => void;
  readonly saving: boolean;
};

const SHIFT_OPTIONS: readonly ShiftOption[] = [
  { label: "Frühschicht (06:00-14:00)", value: "Frueh" },
  { label: "Spätschicht (14:00-22:00)", value: "Spaet" },
  { label: "Nachtschicht (22:00-06:00)", value: "Nacht" },
  { label: "Urlaub", value: "Urlaub" },
  { label: "Frei", value: "Frei" },
];

/**
 * Build the editable draft from one entry.
 */
function draftFromEntry(entry: ShiftplanEntry | null): ShiftplanEditDraft {
  return {
    endTime: entry?.end_time || "",
    notes: entry?.notes || "",
    shift: entry?.shift || "Frueh",
    startTime: entry?.start_time || "",
  };
}

/**
 * Render the shift entry edit dialog controlled by React.
 */
export function ShiftplansEditDialog({
  deleting,
  entry,
  isAdmin,
  message,
  onClose,
  onDelete,
  onSave,
  saving,
}: ShiftplansEditDialogProps): ReactNode {
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const [draft, setDraft] = useState<ShiftplanEditDraft>(() => draftFromEntry(entry));
  const isWorkShift = !["Frei", "Urlaub"].includes(draft.shift);

  useEffect(() => {
    setDraft(draftFromEntry(entry));
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (entry && !dialog.open) {
      dialog.showModal();
      return;
    }
    if (!entry && dialog.open) dialog.close();
  }, [entry]);

  /**
   * Update the selected shift and its default time window.
   */
  function updateShift(value: string): void {
    const window = SHIFT_WINDOWS[value];
    setDraft((current) => ({
      ...current,
      shift: value,
      startTime: window ? window[0] : "",
      endTime: window ? window[1] : "",
    }));
  }

  return (
    <dialog id="sp-dialog" aria-modal="true" aria-labelledby="sp-dlg-title" ref={dialogRef}>
      <div className="card app-card" style={{ minWidth: "320px", maxWidth: "460px", padding: "1.5rem" }}>
        <h3 className="panel-title mb-1" id="sp-dlg-title">
          Eintrag bearbeiten
        </h3>
        <p className="stat-label mb-4" id="sp-dlg-info">
          {entry ? `${entry.employee?.name || ""} - ${entry.work_date}` : ""}
        </p>
        <div className="field mb-3">
          <label htmlFor="dlg-shift">Schicht</label>
          <select className="select select-bordered w-full" id="dlg-shift" value={draft.shift} onChange={(event) => updateShift(event.currentTarget.value)}>
            {SHIFT_OPTIONS.map((shift) => (
              <option key={shift.value} value={shift.value}>
                {shift.label}
              </option>
            ))}
          </select>
        </div>
        <div className="form-grid" id="dlg-times" hidden={!isWorkShift}>
          <div className="field">
            <label htmlFor="dlg-start">Beginn</label>
            <input className="input input-bordered" type="time" id="dlg-start" value={draft.startTime} onChange={(event) => setDraft({ ...draft, startTime: event.currentTarget.value })} />
          </div>
          <div className="field">
            <label htmlFor="dlg-end">Ende</label>
            <input className="input input-bordered" type="time" id="dlg-end" value={draft.endTime} onChange={(event) => setDraft({ ...draft, endTime: event.currentTarget.value })} />
          </div>
        </div>
        <div className="field mb-4">
          <label htmlFor="dlg-notes">Notiz</label>
          <input className="input input-bordered w-full" type="text" id="dlg-notes" placeholder="Optional" value={draft.notes} onChange={(event) => setDraft({ ...draft, notes: event.currentTarget.value })} />
        </div>
        <div className="toolbar">
          <button className="btn btn-primary btn-sm" id="dlg-save" disabled={!entry || saving} type="button" onClick={() => entry && onSave(entry, draft)}>
            {saving ? "Speichert..." : "Speichern"}
          </button>
          <button className="btn btn-error btn-sm" id="dlg-delete" hidden={!isAdmin} disabled={!entry || deleting} type="button" onClick={() => entry && onDelete(entry)}>
            {deleting ? "Löscht..." : "Löschen"}
          </button>
          <button className="btn btn-ghost btn-sm" id="dlg-cancel" type="button" onClick={onClose}>
            Abbrechen
          </button>
        </div>
        <p className={`panel-meta mt-2${message.isError ? " text-error" : ""}`} id="dlg-msg" role="status" aria-live="polite">
          {message.text}
        </p>
      </div>
    </dialog>
  );
}
