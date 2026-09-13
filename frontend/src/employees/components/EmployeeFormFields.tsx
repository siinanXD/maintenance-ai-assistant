import type { ChangeEvent, ReactNode } from "react";

import type { EmployeeDraft } from "../employeeTypes";

type EmployeeFormFieldsProps = {
  readonly draft: EmployeeDraft;
  readonly idPrefix?: string;
  readonly onDraftChange: (draft: EmployeeDraft) => void;
};

/**
 * Return the current field value.
 */
function fieldValue(event: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>): string {
  return event.currentTarget.value;
}

/**
 * Render shared employee form fields.
 */
export function EmployeeFormFields({ draft, idPrefix = "", onDraftChange }: EmployeeFormFieldsProps): ReactNode {
  /**
   * Update one draft field.
   */
  function updateField(field: keyof EmployeeDraft, value: string): void {
    onDraftChange({ ...draft, [field]: value });
  }

  /**
   * Return the DOM id for a form field.
   */
  function id(baseId: string): string {
    return idPrefix ? `${idPrefix}-${baseId}` : baseId;
  }

  return (
    <div className="form-grid">
      <TextField id={id("personnel-number")} label="Personalnummer" name="personnel_number" required value={draft.personnel_number} onChange={(value) => updateField("personnel_number", value)} />
      <TextField id={id("employee-name")} label="Name" name="name" required value={draft.name} onChange={(value) => updateField("name", value)} />
      <TextField id={id("birth-date")} label="Geburtsdatum" name="birth_date" type="date" value={draft.birth_date} onChange={(value) => updateField("birth_date", value)} />
      <TextField id={id("city")} label="Wohnort" name="city" value={draft.city} onChange={(value) => updateField("city", value)} />
      <TextField id={id("street")} label="Strasse" name="street" value={draft.street} onChange={(value) => updateField("street", value)} />
      <TextField id={id("postal-code")} label="Postleitzahl" name="postal_code" value={draft.postal_code} onChange={(value) => updateField("postal_code", value)} />
      <TextField id={id("employee-department")} label="Abteilung" name="department" value={draft.department} onChange={(value) => updateField("department", value)} />
      <div className="field">
        <label htmlFor={id("shift-model")}>Schichtmodell</label>
        <select className="select select-bordered" id={id("shift-model")} name="shift_model" value={draft.shift_model} onChange={(event) => updateField("shift_model", fieldValue(event))}>
          <option value="gleitzeit">Gleitzeit</option>
          <option value="kontischicht">Kontischicht</option>
        </select>
      </div>
      <TextField id={id("current-shift")} label="Aktuelle Schicht / Rhythmus" name="current_shift" value={draft.current_shift} onChange={(value) => updateField("current_shift", value)} />
      <div className="field">
        <label htmlFor={id("team")}>Team 1-5</label>
        <select className="select select-bordered" id={id("team")} name="team" value={draft.team} onChange={(event) => updateField("team", fieldValue(event))}>
          <option value="">-</option>
          <option value="1">Team 1</option>
          <option value="2">Team 2</option>
          <option value="3">Team 3</option>
          <option value="4">Team 4</option>
          <option value="5">Team 5</option>
        </select>
      </div>
      <TextField id={id("salary-group")} label="Gehaltsklasse" name="salary_group" value={draft.salary_group} onChange={(value) => updateField("salary_group", value)} />
      <TextField id={id("favorite-machine")} label="Favoritenmaschine" name="favorite_machine" value={draft.favorite_machine} onChange={(value) => updateField("favorite_machine", value)} />
      <div className="field is-full">
        <label htmlFor={id("qualifications")}>Qualifikationen</label>
        <textarea className="textarea textarea-bordered" id={id("qualifications")} name="qualifications" placeholder="z. B. CNC, Staplerschein, Anlage 4" value={draft.qualifications} onChange={(event) => updateField("qualifications", fieldValue(event))} />
      </div>
    </div>
  );
}

/**
 * Render a controlled employee text input.
 */
function TextField(props: {
  readonly id: string;
  readonly label: string;
  readonly name: keyof EmployeeDraft;
  readonly onChange: (value: string) => void;
  readonly required?: boolean;
  readonly type?: string;
  readonly value: string;
}): ReactNode {
  return (
    <div className="field">
      <label htmlFor={props.id}>{props.label}</label>
      <input className="input input-bordered" id={props.id} name={props.name} required={props.required} type={props.type || "text"} value={props.value} onChange={(event) => props.onChange(fieldValue(event))} />
    </div>
  );
}
