import type { ReactNode } from "react";

import type {
  MaintenanceUser,
  MessageState,
  VacationRequest,
  VacationSummary
} from "../vacationTypes";
import {
  formatVacationDate,
  vacationImpactLabel,
  vacationShiftLabel,
  vacationStatusLabel
} from "../vacationUtils";
import { VacationRequestCard } from "./VacationCards";

type VacationHistoryPanelProps = {
  readonly filteredHistory: readonly VacationRequest[];
  readonly filterStatus: string;
  readonly onFilterStatusChange: (status: string) => void;
  readonly onMessageChange: (message: MessageState) => void;
  readonly onMutated: () => Promise<void>;
  readonly selectedBalanceFor: (employeeId: number) => VacationSummary | null;
  readonly user: MaintenanceUser | null;
};

/**
 * Render vacation history and hidden accessible table body.
 */
export function VacationHistoryPanel(props: VacationHistoryPanelProps): ReactNode {
  return (
    <article className="vacation-history-panel app-card">
      <header className="vacation-panel-header">
        <div>
          <p className="section-kicker">Historie</p>
          <h2>Antragsverlauf</h2>
          <p>Genehmigte, abgelehnte und stornierte Anträge als nachvollziehbare Karten.</p>
        </div>
        <div className="vacation-history-controls">
          <select className="select select-bordered select-sm" value={props.filterStatus} onChange={(event) => props.onFilterStatusChange(event.currentTarget.value)}>
            <option value="">Alle Status</option>
            <option value="approved">Genehmigt</option>
            <option value="rejected">Abgelehnt</option>
            <option value="cancelled">Storniert</option>
            <option value="pending">Ausstehend</option>
          </select>
          <button className="btn btn-outline btn-sm" type="button">Anzeigen</button>
        </div>
      </header>
      <div className="vacation-history-list">
        {props.filteredHistory.length ? props.filteredHistory.map((request) => (
          <VacationRequestCard
            key={request.id}
            mode="history"
            onMessageChange={props.onMessageChange}
            onMutated={props.onMutated}
            request={request}
            selectedBalance={props.selectedBalanceFor(request.employee_id)}
            user={props.user}
          />
        )) : <p className="empty-state">Keine Einträge vorhanden.</p>}
      </div>
      <div className="overflow-x-auto sr-only" aria-hidden="true">
        <table className="table table-sm vacation-history-table">
          <caption>Urlaubsanträge mit Zeitraum, Tagen, Status und Notiz</caption>
          <tbody>
            {props.filteredHistory.map((request) => (
              <tr key={request.id}>
                <td>{request.employee?.name || String(request.employee_id)}</td>
                <td>{formatVacationDate(request.start_date)} - {formatVacationDate(request.end_date)}</td>
                <td>{request.days_used || 0}</td>
                <td>{vacationStatusLabel(request.status)}</td>
                <td>{request.notes || "-"}</td>
                <td>{vacationShiftLabel(request.shift_type)}</td>
                <td>{vacationImpactLabel(request.impact_level)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="empty-state" hidden={props.filteredHistory.length > 0}>Keine Einträge vorhanden.</p>
    </article>
  );
}
