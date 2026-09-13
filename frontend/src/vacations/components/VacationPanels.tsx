import type { ReactNode } from "react";

import type {
  MaintenanceUser,
  MessageState,
  VacationRequest,
  VacationSummary
} from "../vacationTypes";
import { VacationRequestCard } from "./VacationCards";
import { VacationHistoryPanel } from "./VacationHistoryPanel";
import { VacationImpactPanel } from "./VacationImpactPanel";
import { VacationSummaryPanel } from "./VacationSummaryPanel";

type VacationPendingPanelProps = {
  readonly onMessageChange: (message: MessageState) => void;
  readonly onMutated: () => Promise<void>;
  readonly pendingRequests: readonly VacationRequest[];
  readonly selectedBalanceFor: (employeeId: number) => VacationSummary | null;
  readonly selectedYear: string;
  readonly user: MaintenanceUser | null;
  readonly yearOptions: readonly string[];
  readonly onYearChange: (year: string) => void;
};

type VacationOpsPanelsProps = {
  readonly filteredHistory: readonly VacationRequest[];
  readonly filterStatus: string;
  readonly onFilterStatusChange: (status: string) => void;
  readonly onMessageChange: (message: MessageState) => void;
  readonly onMutated: () => Promise<void>;
  readonly requests: readonly VacationRequest[];
  readonly selectedBalanceFor: (employeeId: number) => VacationSummary | null;
  readonly summaries: readonly VacationSummary[];
  readonly user: MaintenanceUser | null;
};

/**
 * Render the pending decision panel.
 */
export function VacationPendingPanel(props: VacationPendingPanelProps): ReactNode {
  return (
    <article className="vacation-decision-panel app-card" id="vacation-decisions">
      <header className="vacation-panel-header">
        <div>
          <p className="section-kicker">Entscheidungen</p>
          <h2>Offene Anträge</h2>
          <p>Genehmigen, ablehnen oder stornieren mit sichtbarer Team- und Resturlaubs-Auswirkung.</p>
        </div>
        <label className="field field-compact" htmlFor="vac-year">
          <span>Jahr</span>
          <select className="select select-bordered select-sm" id="vac-year" value={props.selectedYear} onChange={(event) => props.onYearChange(event.currentTarget.value)}>
            {props.yearOptions.map((year) => <option key={year} value={year}>{year}</option>)}
          </select>
        </label>
      </header>
      <div className="vacation-pending-list">
        <p className="empty-state" hidden={props.pendingRequests.length > 0}>Keine ausstehenden Anträge.</p>
        {props.pendingRequests.map((request) => (
          <VacationRequestCard
            key={request.id}
            mode="pending"
            onMessageChange={props.onMessageChange}
            onMutated={props.onMutated}
            request={request}
            selectedBalance={props.selectedBalanceFor(request.employee_id)}
            user={props.user}
          />
        ))}
      </div>
    </article>
  );
}

/**
 * Render the vacation operations panels below the form.
 */
export function VacationOpsPanels(props: VacationOpsPanelsProps): ReactNode {
  return (
    <section className="vacation-ops-grid" aria-label="Urlaubsstatus und Auswirkungen">
      <VacationImpactPanel requests={props.requests} />
      <VacationSummaryPanel summaries={props.summaries} />
      <VacationHistoryPanel
        filteredHistory={props.filteredHistory}
        filterStatus={props.filterStatus}
        onFilterStatusChange={props.onFilterStatusChange}
        onMessageChange={props.onMessageChange}
        onMutated={props.onMutated}
        selectedBalanceFor={props.selectedBalanceFor}
        user={props.user}
      />
    </section>
  );
}
