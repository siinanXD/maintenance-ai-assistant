import { type FormEvent, type ReactNode } from "react";

import { type DashboardPayload } from "./dashboardApi";
import { dashboardTaskDetailValue, taskDepartmentName, taskText } from "./dashboardTaskModel";

export type ReportState = {
  readonly action: string;
  readonly cause: string;
  readonly generate_report: boolean;
  readonly machine: string;
  readonly result: string;
};

export type ReportTextFieldName = Exclude<keyof ReportState, "generate_report">;

type ReportFieldConfig = {
  readonly fieldName: ReportTextFieldName;
  readonly id: string;
  readonly isTextArea: boolean;
  readonly label: string;
};

export type EditState = {
  readonly department: string;
  readonly description: string;
  readonly due_date: string;
  readonly priority: string;
  readonly status: string;
  readonly title: string;
};

export const REPORT_FIELDS: readonly ReportFieldConfig[] = [
  { id: "report-machine", label: "Maschine", fieldName: "machine", isTextArea: false },
  { id: "report-result", label: "Ergebnis", fieldName: "result", isTextArea: false },
  { id: "report-cause", label: "Ursache", fieldName: "cause", isTextArea: false },
  {
    id: "report-action",
    label: "Maßnahme / Notizen",
    fieldName: "action",
    isTextArea: true
  }
] as const;

const TASK_DETAIL_ROWS = [
  ["Titel", "title"],
  ["Beschreibung", "description"],
  ["Priorität", "priority"],
  ["Status", "status"],
  ["Bereich", "department"],
  ["Ersteller", "creator"],
  ["Erstellt am", "created_at"],
  ["Aktuell bearbeitet von", "current_worker"],
  ["Gestartet am", "started_at"],
  ["Erledigt von", "completed_by_user"],
  ["Erledigt am", "completed_at"]
] as const;

/**
 * Build the initial report state for the controlled completion form.
 */
export function initialReportState(): ReportState {
  return {
    action: "",
    cause: "",
    generate_report: false,
    machine: "",
    result: ""
  };
}

/**
 * Build an edit form state from the active task.
 */
export function editStateFromTask(task: DashboardPayload | null): EditState {
  return {
    department: taskDepartmentName(task),
    description: taskText(task, "description"),
    due_date: taskText(task, "due_date"),
    priority: taskText(task, "priority", "normal"),
    status: taskText(task, "status", "open"),
    title: taskText(task, "title")
  };
}

/**
 * Render one detail row in the dashboard task modal.
 */
function DetailRow({
  label,
  value
}: {
  readonly label: string;
  readonly value: string;
}): ReactNode {
  return (
    <div className="task-detail-row">
      <span>{label}</span>
      <strong>{value || "-"}</strong>
    </div>
  );
}

/**
 * Render the legacy-compatible detail rows for a task.
 */
export function TaskDetailRows({ task }: { readonly task: DashboardPayload | null }): ReactNode {
  return task
    ? TASK_DETAIL_ROWS.map(([label, key]) => (
        <DetailRow key={key} label={label} value={dashboardTaskDetailValue(task, key)} />
      ))
    : null;
}

/**
 * Render one report input while preserving the dashboard runtime hook.
 */
export function ReportField({
  field,
  onChange,
  value
}: {
  readonly field: ReportFieldConfig;
  readonly onChange: (fieldName: ReportTextFieldName, value: string) => void;
  readonly value: string;
}): ReactNode {
  const fieldClassName = field.isTextArea ? "field is-full" : "field";

  return (
    <div className={fieldClassName}>
      <label htmlFor={field.id}>{field.label}</label>
      {field.isTextArea ? (
        <textarea
          className="textarea textarea-bordered"
          id={field.id}
          data-report-field={field.fieldName}
          value={value}
          onChange={(event) => onChange(field.fieldName, event.target.value)}
        />
      ) : (
        <input
          className="input input-bordered"
          id={field.id}
          data-report-field={field.fieldName}
          value={value}
          onChange={(event) => onChange(field.fieldName, event.target.value)}
        />
      )}
    </div>
  );
}

/**
 * Render the editable task detail form.
 */
export function TaskEditForm({
  editState,
  isBusy,
  onChange,
  onSubmit
}: {
  readonly editState: EditState;
  readonly isBusy: boolean;
  readonly onChange: (key: keyof EditState, value: string) => void;
  readonly onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}): ReactNode {
  return (
    <form className="task-detail-row md:col-span-2" data-task-edit-form="true" onSubmit={onSubmit}>
      <div className="form-grid">
        <label className="field">
          <span>Titel</span>
          <input className="input input-bordered" name="title" required value={editState.title} onChange={(event) => onChange("title", event.target.value)} />
        </label>
        <label className="field">
          <span>Bereich</span>
          <input className="input input-bordered" name="department" required value={editState.department} onChange={(event) => onChange("department", event.target.value)} />
        </label>
        <label className="field">
          <span>Priorität</span>
          <select className="select select-bordered" name="priority" value={editState.priority} onChange={(event) => onChange("priority", event.target.value)}>
            <option value="urgent">urgent</option>
            <option value="soon">soon</option>
            <option value="normal">normal</option>
            <option value="low">low</option>
          </select>
        </label>
        <label className="field">
          <span>Status</span>
          <select className="select select-bordered" name="status" value={editState.status} onChange={(event) => onChange("status", event.target.value)}>
            <option value="open">open</option>
            <option value="in_progress">in_progress</option>
            <option value="done">done</option>
            <option value="cancelled">cancelled</option>
          </select>
        </label>
        <label className="field">
          <span>Fällig am</span>
          <input className="input input-bordered" name="due_date" type="date" value={editState.due_date} onChange={(event) => onChange("due_date", event.target.value)} />
        </label>
        <label className="field is-full">
          <span>Beschreibung</span>
          <textarea className="textarea textarea-bordered" name="description" value={editState.description} onChange={(event) => onChange("description", event.target.value)} />
        </label>
      </div>
      <div className="toolbar form-actions">
        <button className="btn btn-primary" disabled={isBusy} type="submit">
          Änderungen speichern
        </button>
      </div>
    </form>
  );
}
