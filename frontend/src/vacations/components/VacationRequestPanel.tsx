import type { FormEvent, ReactNode } from "react";

import { createVacationRequest } from "../vacationApi";
import type {
  Employee,
  MessageState,
  VacationDraft,
  VacationImpact,
  VacationSummary
} from "../vacationTypes";
import {
  countVacationWorkdays,
  employeeOptionLabel,
  EMPTY_VACATION_DRAFT,
  representativeAllowed,
  todayDateInputValue,
  vacationErrorMessage,
  vacationValidationError
} from "../vacationUtils";
import { BalancePreview } from "./VacationRequestPreviews";

type VacationRequestPanelProps = {
  readonly draft: VacationDraft;
  readonly employees: readonly Employee[];
  readonly impact: VacationImpact | null;
  readonly impactMessage: MessageState;
  readonly message: MessageState;
  readonly onDraftChange: (draft: VacationDraft) => void;
  readonly onMessageChange: (message: MessageState) => void;
  readonly onSaved: () => Promise<void>;
  readonly selectedBalance: VacationSummary | null;
  readonly selectedEmployee: Employee | null;
  readonly submitDisabled: boolean;
};

/**
 * Render the vacation request form.
 */
export function VacationRequestPanel(props: VacationRequestPanelProps): ReactNode {
  const days = countVacationWorkdays(props.draft.startDate, props.draft.endDate);
  const today = todayDateInputValue();

  /**
   * Update one draft field.
   */
  function updateDraft(field: keyof VacationDraft, value: string): void {
    const nextDraft = { ...props.draft, [field]: value };
    if (field === "employeeId" && value === nextDraft.representativeEmployeeId) {
      nextDraft.representativeEmployeeId = "";
    }
    props.onDraftChange(nextDraft);
  }

  /**
   * Submit the vacation request.
   */
  async function submitVacation(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const error = vacationValidationError(props.draft, props.selectedBalance);
    if (!props.draft.employeeId || !props.draft.startDate || !props.draft.endDate) {
      props.onMessageChange({ text: "Bitte alle Pflichtfelder ausfüllen.", type: "error" });
      return;
    }
    if (error) {
      props.onMessageChange({ text: error, type: "error" });
      return;
    }

    props.onMessageChange({ text: "Antrag wird gesendet...", type: "" });
    try {
      await createVacationRequest(props.draft);
      props.onDraftChange({ ...EMPTY_VACATION_DRAFT });
      props.onMessageChange({ text: "Antrag gestellt.", type: "success" });
      await props.onSaved();
    } catch (requestError) {
      props.onMessageChange({ text: vacationErrorMessage(requestError), type: "error" });
    }
  }

  return (
    <article className="vacation-request-panel app-card" id="vacation-request">
      <header className="vacation-panel-header">
        <div>
          <p className="section-kicker">Antrag</p>
          <h2>Urlaub beantragen</h2>
          <p>Zeitraum, Schichtbezug und Vertreter werden direkt gegen Resturlaub und Teamlage geprüft.</p>
        </div>
      </header>
      <form className="vacation-form" onSubmit={submitVacation}>
        <div className="field is-full">
          <label htmlFor="vac-employee">Mitarbeiter *</label>
          <select className="select select-bordered" id="vac-employee" required value={props.draft.employeeId} onChange={(event) => updateDraft("employeeId", event.currentTarget.value)}>
            <option value="" disabled>Bitte wählen...</option>
            {props.employees.map((employee) => <option key={employee.id} value={employee.id}>{employeeOptionLabel(employee)}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="vac-start">Von *</label>
          <input className="input input-bordered" id="vac-start" min={today} required type="date" value={props.draft.startDate} onChange={(event) => updateDraft("startDate", event.currentTarget.value)} />
        </div>
        <div className="field">
          <label htmlFor="vac-end">Bis *</label>
          <input className="input input-bordered" id="vac-end" min={today} required type="date" value={props.draft.endDate} onChange={(event) => updateDraft("endDate", event.currentTarget.value)} />
        </div>
        <div className="field">
          <label htmlFor="vac-shift">Schichtbezug</label>
          <select className="select select-bordered" id="vac-shift" value={props.draft.shiftType} onChange={(event) => updateDraft("shiftType", event.currentTarget.value)}>
            <option value="">Keine feste Schicht</option>
            <option value="Frueh">Früh</option>
            <option value="Spaet">Spät</option>
            <option value="Nacht">Nacht</option>
            <option value="Tag">Tagdienst</option>
            <option value="Alle">Alle Schichten</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="vac-representative">Vertreter</label>
          <select className="select select-bordered" id="vac-representative" value={props.draft.representativeEmployeeId} onChange={(event) => updateDraft("representativeEmployeeId", event.currentTarget.value)}>
            <option value="">Noch nicht festgelegt</option>
            {props.employees.filter((employee) => representativeAllowed(props.selectedEmployee, employee)).map((employee) => <option key={employee.id} value={employee.id}>{employeeOptionLabel(employee)}</option>)}
          </select>
        </div>
        <div className="field is-full">
          <label htmlFor="vac-reason">Grund</label>
          <input className="input input-bordered" id="vac-reason" maxLength={160} placeholder="Optional, z. B. Erholungsurlaub" type="text" value={props.draft.reason} onChange={(event) => updateDraft("reason", event.currentTarget.value)} />
        </div>
        <div className="field is-full">
          <label htmlFor="vac-notes">Notiz</label>
          <input className="input input-bordered" id="vac-notes" maxLength={500} placeholder="Optionaler Hinweis für Genehmiger" type="text" value={props.draft.notes} onChange={(event) => updateDraft("notes", event.currentTarget.value)} />
        </div>
        <BalancePreview draft={props.draft} selectedBalance={props.selectedBalance} selectedEmployee={props.selectedEmployee} />
        <div className={`vacation-impact-preview is-full${props.impactMessage.type ? ` is-${props.impactMessage.type}` : props.impact?.level ? ` is-${props.impact.level}` : ""}`}>
          {props.impactMessage.text}
        </div>
        <div className="field is-full" hidden={days === null}>
          <span className="panel-meta">Arbeitstage: </span>
          <span className="badge badge-neutral">{days === null ? "-" : `${days} Arbeitstage`}</span>
        </div>
        <div className="vacation-form-footer">
          <button className="btn btn-primary" disabled={props.submitDisabled} type="submit">Antrag stellen</button>
          <p className={`form-message${props.message.type ? ` is-${props.message.type}` : ""}`} role="status" aria-live="polite">{props.message.text}</p>
        </div>
      </form>
    </article>
  );
}
