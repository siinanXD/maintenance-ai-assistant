import { type ChangeEvent, type ReactNode } from "react";

import { todayIsoDate } from "../../utils/date";
import {
  DEPARTMENT_OPTIONS,
  MACHINE_STATUS_OPTIONS,
  PROBLEM_CATEGORY_OPTIONS,
  PRODUCTION_STATUS_OPTIONS,
  SHIFT_OPTIONS,
} from "../handoverOptions";
import { adjacentShift } from "../handoverUtils";
import type { Machine } from "../handoverTypes";

type FieldProps = {
  readonly children: ReactNode;
  readonly className?: string;
};

type TextAreaField = {
  readonly className?: string;
  readonly id: string;
  readonly label: string;
  readonly name: string;
  readonly placeholder?: string;
  readonly rows: number;
};

const PROBLEM_TEXT_AREAS: readonly TextAreaField[] = [
  {
    id: "ho-content",
    label: "Status der aktuellen Schicht",
    name: "content",
    rows: 3,
    className: "field is-full",
    placeholder: "Was wurde erledigt? Was war die Lage in der Schicht?",
  },
  { id: "ho-machine-notes", label: "Maschinenstatus / Auffälligkeiten", name: "machine_notes", rows: 3 },
  { id: "ho-cause", label: "Ursache", name: "cause", rows: 3 },
  { id: "ho-action", label: "Maßnahme", name: "action_taken", rows: 3 },
  { id: "ho-safety", label: "Sicherheitsrelevante Hinweise", name: "safety_notes", rows: 3 },
  {
    id: "ho-material",
    label: "Material- / Ersatzteilhinweise",
    name: "material_notes",
    rows: 2,
    className: "field is-full",
  },
];

const FOLLOW_UP_TEXT_AREAS: readonly TextAreaField[] = [
  { id: "ho-open-tasks", label: "Offene Tasks", name: "open_tasks", rows: 3 },
  { id: "ho-follow-up", label: "Offene Folgeaufgabe", name: "follow_up_task", rows: 3 },
  {
    id: "ho-next-notes",
    label: "Hinweise für nächste Schicht",
    name: "next_notes",
    rows: 3,
    className: "field is-full",
  },
];

/**
 * Render one form field wrapper.
 */
function Field({ children, className = "field" }: FieldProps): ReactNode {
  return <div className={className}>{children}</div>;
}

/**
 * Render one selectable option list with an optional placeholder.
 */
function OptionList({
  options,
  placeholder,
}: {
  readonly options: readonly { label: string; value: string }[];
  readonly placeholder?: string;
}): ReactNode {
  return (
    <>
      {placeholder ? <option value="">{placeholder}</option> : null}
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </>
  );
}

/**
 * Render one handover workflow step.
 */
function HandoverStep({
  children,
  description,
  number,
  title,
}: {
  readonly children: ReactNode;
  readonly description: string;
  readonly number: string;
  readonly title: string;
}): ReactNode {
  return (
    <section className="handover-step">
      <header>
        <span>{number}</span>
        <div>
          <strong>{title}</strong>
          <small>{description}</small>
        </div>
      </header>
      {children}
    </section>
  );
}

/**
 * Render one textarea field used by the handover form.
 */
function HandoverTextArea({ className = "field", id, label, name, placeholder, rows }: TextAreaField): ReactNode {
  return (
    <Field className={className}>
      <label htmlFor={id}>{label}</label>
      <textarea className="textarea textarea-bordered" id={id} name={name} rows={rows} placeholder={placeholder} />
    </Field>
  );
}

/**
 * Keep previous and next shift fields aligned with the selected shift.
 */
function handleShiftChange(event: ChangeEvent<HTMLSelectElement>): void {
  const form = event.currentTarget.form;
  if (!form || !event.currentTarget.value) return;

  const previous = form.elements.namedItem("previous_shift");
  const next = form.elements.namedItem("next_shift");
  if (previous instanceof HTMLSelectElement) previous.value = adjacentShift(event.currentTarget.value, -1);
  if (next instanceof HTMLSelectElement) next.value = adjacentShift(event.currentTarget.value, 1);
}

/**
 * Render the shift selection step.
 */
export function ShiftStep(): ReactNode {
  return (
    <HandoverStep number="1" title="Schicht auswählen" description="Aktuelle, vorherige und nächste Schicht festlegen.">
      <div className="form-grid">
        <Field>
          <label htmlFor="ho-department">Bereich *</label>
          <select className="select select-bordered" id="ho-department" name="department" required defaultValue="">
            <option value="" disabled>
              Bitte wählen
            </option>
            <OptionList options={DEPARTMENT_OPTIONS} />
          </select>
        </Field>
        <Field>
          <label htmlFor="ho-date">Datum *</label>
          <input className="input input-bordered" id="ho-date" name="shift_date" type="date" required defaultValue={todayIsoDate()} />
        </Field>
        <Field>
          <label htmlFor="ho-shift-type">Aktuelle Schicht *</label>
          <select className="select select-bordered" id="ho-shift-type" name="shift_type" required defaultValue="" onChange={handleShiftChange}>
            <option value="" disabled>
              Bitte wählen
            </option>
            <OptionList options={SHIFT_OPTIONS} />
          </select>
        </Field>
        <Field>
          <label htmlFor="ho-previous-shift">Vorherige Schicht</label>
          <select className="select select-bordered" id="ho-previous-shift" name="previous_shift">
            <OptionList options={SHIFT_OPTIONS} placeholder="Automatisch" />
          </select>
        </Field>
        <Field>
          <label htmlFor="ho-next-shift">Nächste Schicht</label>
          <select className="select select-bordered" id="ho-next-shift" name="next_shift">
            <OptionList options={SHIFT_OPTIONS} placeholder="Automatisch" />
          </select>
        </Field>
      </div>
    </HandoverStep>
  );
}

/**
 * Render the machine and responsible people step.
 */
export function AssignmentStep({ machines }: { readonly machines: readonly Machine[] }): ReactNode {
  return (
    <HandoverStep number="2" title="Maschine und Verantwortliche" description="Bereich, Anlage und beteiligte Personen eindeutig zuordnen.">
      <div className="form-grid">
        <Field>
          <label htmlFor="ho-area">Linie / Teilbereich</label>
          <input className="input input-bordered" id="ho-area" name="area" placeholder="z. B. Linie 2, Verpackung, EOL" />
        </Field>
        <Field>
          <label htmlFor="ho-machine-id">Maschine</label>
          <select className="select select-bordered" id="ho-machine-id" name="machine_id">
            <option value="">Keine Maschine zugeordnet</option>
            {machines.map((machine) => (
              <option key={machine.id} value={machine.id}>
                {machine.name}
              </option>
            ))}
          </select>
        </Field>
        <Field>
          <label htmlFor="ho-responsible">Verantwortlicher Mitarbeiter</label>
          <input className="input input-bordered" id="ho-responsible" name="responsible_employee" />
        </Field>
        <Field>
          <label htmlFor="ho-involved">Beteiligte Mitarbeiter</label>
          <input className="input input-bordered" id="ho-involved" name="involved_employees" placeholder="Namen oder Team" />
        </Field>
      </div>
    </HandoverStep>
  );
}

/**
 * Render the status selection step.
 */
export function StatusStep(): ReactNode {
  return (
    <HandoverStep number="3" title="Status erfassen" description="Produktions-, Maschinen- und Problemstatus strukturiert festhalten.">
      <div className="form-grid">
        <Field>
          <label htmlFor="ho-production-status">Produktionsstatus</label>
          <select className="select select-bordered" id="ho-production-status" name="production_status">
            <OptionList options={PRODUCTION_STATUS_OPTIONS} placeholder="Nicht bewertet" />
          </select>
        </Field>
        <Field>
          <label htmlFor="ho-machine-status">Maschinenstatus</label>
          <select className="select select-bordered" id="ho-machine-status" name="machine_status">
            <OptionList options={MACHINE_STATUS_OPTIONS} placeholder="Nicht bewertet" />
          </select>
        </Field>
        <Field>
          <label htmlFor="ho-category">Kategorie</label>
          <select className="select select-bordered" id="ho-category" name="problem_category">
            <option value="">Keine Kategorie</option>
            {PROBLEM_CATEGORY_OPTIONS.map((category) => (
              <option key={category}>{category}</option>
            ))}
          </select>
        </Field>
        <Field>
          <label htmlFor="ho-duration">Dauer in Minuten</label>
          <input className="input input-bordered" id="ho-duration" name="duration_minutes" type="number" min="0" step="1" />
        </Field>
      </div>
    </HandoverStep>
  );
}

/**
 * Render the problem notes step.
 */
export function ProblemStep(): ReactNode {
  return (
    <HandoverStep number="4" title="Probleme und Maßnahmen" description="Ursache, Maßnahme, Sicherheits- und Materialhinweise getrennt erfassen.">
      <div className="form-grid">
        {PROBLEM_TEXT_AREAS.map((field) => (
          <HandoverTextArea key={field.id} {...field} />
        ))}
      </div>
    </HandoverStep>
  );
}

/**
 * Render the follow-up notes step.
 */
export function FollowUpStep(): ReactNode {
  return (
    <HandoverStep number="5" title="Offene Punkte übergeben" description="Folgeaufgaben und klare Hinweise für die nächste Schicht speichern.">
      <div className="form-grid">
        {FOLLOW_UP_TEXT_AREAS.map((field) => (
          <HandoverTextArea key={field.id} {...field} />
        ))}
      </div>
    </HandoverStep>
  );
}
