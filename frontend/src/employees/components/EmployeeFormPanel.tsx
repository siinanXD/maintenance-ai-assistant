import type { FormEvent, ReactNode } from "react";

import { createEmployee } from "../employeeApi";
import type { EmployeeDraft, MessageState } from "../employeeTypes";
import { EMPTY_EMPLOYEE_DRAFT, employeeErrorMessage } from "../employeeUtils";
import { EmployeeFormFields } from "./EmployeeFormFields";

type EmployeeFormPanelProps = {
  readonly drawerMode?: boolean;
  readonly draft: EmployeeDraft;
  readonly hidden: boolean;
  readonly message: MessageState;
  readonly onDraftChange: (draft: EmployeeDraft) => void;
  readonly onMessageChange: (message: MessageState) => void;
  readonly onSaved: () => Promise<void>;
};

/**
 * Render the employee create form.
 */
export function EmployeeFormPanel(props: EmployeeFormPanelProps): ReactNode {
  /**
   * Create a new employee and refresh the list.
   */
  async function submitEmployee(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    props.onMessageChange({ text: "Mitarbeiter wird gespeichert...", error: false });
    try {
      await createEmployee(props.draft);
      props.onDraftChange({ ...EMPTY_EMPLOYEE_DRAFT });
      await props.onSaved();
      props.onMessageChange({ text: "Mitarbeiter gespeichert.", error: false });
    } catch (error) {
      props.onMessageChange({ text: employeeErrorMessage(error), error: true });
    }
  }

  return (
    <details className="card app-card mobile-action-section lg:col-span-12" hidden={props.hidden} open={props.drawerMode ?? true}>
      <summary className="mobile-action-summary">
        <span>
          <span className="mobile-action-title">Mitarbeiter anlegen</span>
          <span className="mobile-action-meta">Stammdaten und Qualifikationen erfassen</span>
        </span>
      </summary>
      <form onSubmit={submitEmployee}>
        <div className="card-body">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Mitarbeiter anlegen</h2>
              <p className="panel-meta">Personalnummer, Stammdaten, Schicht, Team, Qualifikationen und Lieblingsmaschine</p>
            </div>
          </div>
          <EmployeeFormFields draft={props.draft} onDraftChange={props.onDraftChange} />
          <div className="toolbar form-actions">
            <button className="btn btn-primary" type="submit">Mitarbeiter speichern</button>
            <span className={`panel-meta${props.message.error ? " is-error" : ""}`}>{props.message.text}</span>
          </div>
        </div>
      </form>
    </details>
  );
}
