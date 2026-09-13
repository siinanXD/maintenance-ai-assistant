import { useEffect, useState, type ChangeEvent, type ReactNode } from "react";

import { updateEmployee } from "../employeeApi";
import type { Employee, EmployeeDraft, MessageState } from "../employeeTypes";
import { draftFromEmployee, employeeErrorMessage } from "../employeeUtils";

type EmployeeEditDialogProps = {
  readonly employee: Employee | null;
  readonly onClose: () => void;
  readonly onMessageChange: (message: MessageState) => void;
  readonly onSaved: () => Promise<void>;
};

/**
 * Return one controlled field value from an input event.
 */
function inputValue(event: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>): string {
  return event.currentTarget.value;
}

/**
 * Render one labelled text input of the edit dialog.
 */
function EditTextField(props: {
  readonly id: string;
  readonly label: string;
  readonly onChange: (value: string) => void;
  readonly required?: boolean;
  readonly type?: string;
  readonly value: string;
}): ReactNode {
  return (
    <div className="field">
      <label htmlFor={props.id}>{props.label}</label>
      <input
        className="input input-bordered"
        id={props.id}
        required={props.required}
        type={props.type || "text"}
        value={props.value}
        onChange={(event) => props.onChange(inputValue(event))}
      />
    </div>
  );
}

/**
 * Render the employee edit dialog.
 */
export function EmployeeEditDialog(props: EmployeeEditDialogProps): ReactNode {
  const [draft, setDraft] = useState<EmployeeDraft>(draftFromEmployee(props.employee));
  const [dialogMessage, setDialogMessage] = useState<MessageState>({ text: "", error: false });

  useEffect(() => {
    setDraft(draftFromEmployee(props.employee));
    setDialogMessage({ text: "", error: false });
  }, [props.employee]);

  /**
   * Update one field in the edit draft.
   */
  function updateField(field: keyof EmployeeDraft, value: string): void {
    setDraft((currentDraft) => ({ ...currentDraft, [field]: value }));
  }

  /**
   * Save the selected employee.
   */
  async function saveEmployee(): Promise<void> {
    if (!props.employee) return;
    setDialogMessage({ text: "Wird gespeichert...", error: false });
    try {
      await updateEmployee(props.employee.id, draft);
      await props.onSaved();
      props.onMessageChange({ text: "Mitarbeiter aktualisiert.", error: false });
      props.onClose();
    } catch (error) {
      setDialogMessage({ text: employeeErrorMessage(error), error: true });
    }
  }

  return (
    <dialog aria-labelledby="empd-title" aria-modal="true" id="emp-edit-dialog" open={Boolean(props.employee)}>
      <div className="card app-card" style={{ maxHeight: "90vh", maxWidth: "560px", minWidth: "320px", overflowY: "auto", padding: "1.5rem" }}>
        <h3 className="panel-title mb-4" id="empd-title">Mitarbeiter bearbeiten</h3>
        <input id="empd-id" type="hidden" value={props.employee?.id || ""} readOnly />
        <div className="form-grid">
          <EditTextField id="empd-pnr" label="Personalnummer" value={draft.personnel_number} onChange={(value) => updateField("personnel_number", value)} />
          <EditTextField id="empd-name" label="Name" required value={draft.name} onChange={(value) => updateField("name", value)} />
          <EditTextField id="empd-birth" label="Geburtsdatum" type="date" value={draft.birth_date} onChange={(value) => updateField("birth_date", value)} />
          <EditTextField id="empd-city" label="Wohnort" value={draft.city} onChange={(value) => updateField("city", value)} />
          <EditTextField id="empd-street" label="Strasse" value={draft.street} onChange={(value) => updateField("street", value)} />
          <EditTextField id="empd-postal" label="Postleitzahl" value={draft.postal_code} onChange={(value) => updateField("postal_code", value)} />
          <EditTextField id="empd-dept" label="Abteilung" value={draft.department} onChange={(value) => updateField("department", value)} />
          <div className="field">
            <label htmlFor="empd-shift-model">Schichtmodell</label>
            <select className="select select-bordered" id="empd-shift-model" value={draft.shift_model} onChange={(event) => updateField("shift_model", inputValue(event))}>
              <option value="gleitzeit">Gleitzeit</option>
              <option value="kontischicht">Kontischicht</option>
            </select>
          </div>
          <EditTextField id="empd-current-shift" label="Aktuelle Schicht / Rhythmus" value={draft.current_shift} onChange={(value) => updateField("current_shift", value)} />
          <div className="field">
            <label htmlFor="empd-team">Team 1-5</label>
            <select className="select select-bordered" id="empd-team" value={draft.team} onChange={(event) => updateField("team", inputValue(event))}>
              <option value="">-</option>
              <option value="1">Team 1</option>
              <option value="2">Team 2</option>
              <option value="3">Team 3</option>
              <option value="4">Team 4</option>
              <option value="5">Team 5</option>
            </select>
          </div>
          <EditTextField id="empd-salary" label="Gehaltsklasse" value={draft.salary_group} onChange={(value) => updateField("salary_group", value)} />
          <EditTextField id="empd-machine" label="Favoritenmaschine" value={draft.favorite_machine} onChange={(value) => updateField("favorite_machine", value)} />
          <div className="field is-full">
            <label htmlFor="empd-qualifications">Qualifikationen</label>
            <textarea className="textarea textarea-bordered" id="empd-qualifications" value={draft.qualifications} onChange={(event) => updateField("qualifications", inputValue(event))} />
          </div>
        </div>
        <div className="toolbar mt-4">
          <button className="btn btn-primary btn-sm" id="empd-save" type="button" onClick={saveEmployee}>Speichern</button>
          <button className="btn btn-ghost btn-sm" id="empd-cancel" type="button" onClick={props.onClose}>Abbrechen</button>
        </div>
        <p className={`panel-meta mt-2${dialogMessage.error ? " is-error" : ""}`} id="empd-msg" role="status" aria-live="polite">{dialogMessage.text}</p>
      </div>
    </dialog>
  );
}
