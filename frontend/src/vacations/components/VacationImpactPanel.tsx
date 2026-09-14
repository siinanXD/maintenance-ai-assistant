import type { ReactNode } from "react";

import type { VacationRequest } from "../vacationTypes";
import { formatVacationDate, vacationStatusLabel } from "../vacationUtils";

type VacationImpactPanelProps = {
  readonly requests: readonly VacationRequest[];
};

/**
 * Return the latest active vacations for the operations list.
 */
function activeVacationRequests(requests: readonly VacationRequest[]): VacationRequest[] {
  return requests
    .filter((request) => ["pending", "approved"].includes(request.status || ""))
    .sort((first, second) => String(first.start_date || "").localeCompare(String(second.start_date || "")))
    .slice(0, 8);
}

/**
 * Return the visible team status summary.
 */
function teamStatusText(requests: readonly VacationRequest[]): string {
  const active = activeVacationRequests(requests);
  if (!active.length) return "Keine offenen Personalwarnungen.";
  const critical = active.filter((request) => request.impact_level === "critical").length;
  const warning = active.filter((request) => request.impact_level === "warning").length;
  if (critical) return `${critical} kritische Personalhinweise`;
  if (warning) return `${warning} Warnhinweise im Team`;
  return "Teamlage ohne auffällige Konflikte.";
}

/**
 * Render active vacation impact information.
 */
export function VacationImpactPanel(props: VacationImpactPanelProps): ReactNode {
  const activeRequests = activeVacationRequests(props.requests);

  return (
    <article className="vacation-impact-panel app-card">
      <header className="vacation-panel-header">
        <div>
          <p className="section-kicker">Betrieb</p>
          <h2>Auswirkungen</h2>
          <p>{teamStatusText(props.requests)}</p>
        </div>
      </header>
      <div className="vacation-calendar-list">
        {activeRequests.length ? activeRequests.map((request) => (
          <article className={`vacation-calendar-item is-${request.impact_level || "ok"}`} key={request.id}>
            <strong>{request.employee?.name || String(request.employee_id)}</strong>
            <p className="vacation-card-meta">
              {[
                `${formatVacationDate(request.start_date)} bis ${formatVacationDate(request.end_date)}`,
                vacationStatusLabel(request.status),
                request.impact_summary || "keine Warnung"
              ].join(" · ")}
            </p>
          </article>
        )) : <div className="empty-state">Keine aktiven Urlaubszeiträume im ausgewählten Jahr.</div>}
      </div>
    </article>
  );
}
