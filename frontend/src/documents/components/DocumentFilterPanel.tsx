import type { ChangeEvent, FormEvent, ReactNode } from "react";

import type { DocumentFilters, MessageState } from "../documentTypes";
import { emptyDocumentFilters } from "../documentUtils";

type DocumentFilterPanelProps = {
  readonly drawerMode?: boolean;
  readonly filters: DocumentFilters;
  readonly message: MessageState;
  readonly onFiltersChange: (filters: DocumentFilters) => void;
  readonly onSubmit: () => Promise<void>;
};

/**
 * Return an input value.
 */
function inputValue(event: ChangeEvent<HTMLInputElement>): string {
  return event.currentTarget.value;
}

/**
 * Render generated document filter controls.
 */
export function DocumentFilterPanel({ drawerMode = false, filters, message, onFiltersChange, onSubmit }: DocumentFilterPanelProps): ReactNode {
  /**
   * Submit the current filters.
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    await onSubmit();
  }

  return (
    <details className="card app-card mobile-action-section lg:order-3 lg:col-span-12" open={drawerMode}>
      <summary className="mobile-action-summary">
        <span>
          <span className="mobile-action-title">Filter</span>
          <span className="mobile-action-meta">Dokumente gezielt eingrenzen</span>
        </span>
      </summary>
      <form onSubmit={handleSubmit}>
        <div className="card-body">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Filter</h2>
              <p className="panel-meta">Nach Aufgabe, Bereich, Maschine oder Datum suchen</p>
            </div>
          </div>
          <div className="form-grid">
            <FilterInput id="document-task-id" label="Aufgaben-ID" name="task_id" type="number" value={filters.task_id} onChange={(value) => onFiltersChange({ ...filters, task_id: value })} />
            <FilterInput id="document-department" label="Bereich" name="department" value={filters.department} onChange={(value) => onFiltersChange({ ...filters, department: value })} />
            <FilterInput id="document-machine" label="Maschine" name="machine" value={filters.machine} onChange={(value) => onFiltersChange({ ...filters, machine: value })} />
            <FilterInput id="document-date-from" label="Von" name="date_from" type="date" value={filters.date_from} onChange={(value) => onFiltersChange({ ...filters, date_from: value })} />
            <FilterInput id="document-date-to" label="Bis" name="date_to" type="date" value={filters.date_to} onChange={(value) => onFiltersChange({ ...filters, date_to: value })} />
          </div>
          <div className="toolbar form-actions">
            <button className="btn btn-primary" type="submit">Filtern</button>
            <button className="btn btn-ghost" type="button" onClick={() => onFiltersChange(emptyDocumentFilters())}>Zurücksetzen</button>
            <span className={`panel-meta${message.error ? " is-error" : ""}`}>{message.text}</span>
          </div>
        </div>
      </form>
    </details>
  );
}

/**
 * Render one filter input.
 */
function FilterInput(props: {
  readonly id: string;
  readonly label: string;
  readonly name: keyof DocumentFilters;
  readonly onChange: (value: string) => void;
  readonly type?: string;
  readonly value: string;
}): ReactNode {
  return (
    <div className="field">
      <label htmlFor={props.id}>{props.label}</label>
      <input className="input input-bordered" id={props.id} min={props.type === "number" ? "1" : undefined} name={props.name} type={props.type || "text"} value={props.value} onChange={(event) => props.onChange(inputValue(event))} />
    </div>
  );
}
