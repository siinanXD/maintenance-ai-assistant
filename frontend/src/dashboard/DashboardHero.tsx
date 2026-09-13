import { type ReactNode } from "react";

import { canWriteDashboard } from "../auth/permissions";
import { type DashboardStatusChipState, type DashboardViewState } from "./dashboardModel";
import { dashboardHeroStatus } from "./dashboardTechnicalModel";

type DashboardHeroProps = {
  readonly dashboardState: DashboardViewState;
  readonly statusChips: readonly DashboardStatusChipState[];
};

/**
 * Build a React data-attribute object for runtime selectors.
 */
function dataHookAttribute(hookName: string): Record<string, string> {
  return { [hookName]: "" };
}

/**
 * Render one hidden secondary status hook for legacy runtime selectors.
 */
function DashboardStatusHook({ chip }: { readonly chip: DashboardStatusChipState }): ReactNode {
  return (
    <span>
      <strong {...dataHookAttribute(chip.valueHook)}>{chip.value}</strong>
      <span>{chip.label}</span>
      {chip.metaHook ? <small {...dataHookAttribute(chip.metaHook)}>{chip.meta}</small> : null}
    </span>
  );
}

/**
 * Render the dashboard control-center topbar with the existing runtime hooks.
 */
export function DashboardHero({ dashboardState, statusChips }: DashboardHeroProps): ReactNode {
  const status = dashboardHeroStatus(
    dashboardState.data,
    dashboardState.isLoading,
    dashboardState.errorMessage
  );
  const canCreateTasks = canWriteDashboard("tasks");
  const canCreateIncidents = canWriteDashboard("errors");

  return (
    <section
      className="control-center-topbar"
      data-ai-ops-cockpit=""
      aria-label="Maintenance Control Center"
    >
      <div className="control-center-copy">
        <p className="page-kicker">Maintenance Control Center</p>
        <h1 className="page-title">Aktuelle Lage im Werk</h1>
      </div>
      <div className="control-center-status" aria-label="Aktueller Betriebsstatus">
        <span className={`ops-status-pill ${status.className}`} data-ai-ops-status="">
          {status.label}
        </span>
        <span data-ai-ops-updated="">{status.updated}</span>
        <span data-dashboard-system-meta="">{status.meta}</span>
      </div>
      <div className="dashboard-status-hook-row" aria-label="Sekundäre Statuswerte" hidden>
        {statusChips.map((chip) => (
          <DashboardStatusHook key={chip.valueHook} chip={chip} />
        ))}
      </div>
      <div className="control-center-actions" aria-label="Schnellzugriff">
        {canCreateTasks ? (
          <a className="btn btn-primary btn-sm" data-dashboard-nav="tasks" href="/tasks#task-create">
            Aufgabe anlegen
          </a>
        ) : null}
        {canCreateIncidents ? (
          <a className="btn btn-outline btn-sm" data-dashboard-nav="errors" href="/errors#incident-create">
            St&ouml;rung melden
          </a>
        ) : null}
      </div>
    </section>
  );
}
