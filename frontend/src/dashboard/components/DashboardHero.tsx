import { type ReactNode } from "react";

import { canWriteDashboard } from "../../auth/permissions";
import { type DashboardViewState } from "../dashboardModel";
import { dashboardHeroStatus } from "../dashboardTechnicalModel";

/**
 * Render the cockpit title, the data status and the two quick actions.
 */
export function DashboardHero({ dashboardState }: { readonly dashboardState: DashboardViewState }): ReactNode {
  const status = dashboardHeroStatus(
    dashboardState.data,
    dashboardState.isLoading,
    dashboardState.errorMessage
  );

  return (
    <section className="control-center-topbar" aria-label="Maintenance Control Center">
      <div className="control-center-copy">
        <p className="page-kicker">Maintenance Control Center</p>
        <h1 className="page-title">Aktuelle Lage im Werk</h1>
      </div>
      <div className="control-center-status" aria-label="Aktueller Betriebsstatus">
        <span className={`ops-status-pill ${status.className}`}>{status.label}</span>
        <span>{status.updated}</span>
        <span>{status.meta}</span>
      </div>
      <div className="control-center-actions" aria-label="Schnellzugriff">
        {canWriteDashboard("tasks") ? (
          <a className="btn btn-primary btn-sm" href="/tasks#task-create">Aufgabe anlegen</a>
        ) : null}
        {canWriteDashboard("errors") ? (
          <a className="btn btn-outline btn-sm" href="/errors#incident-create">Störung melden</a>
        ) : null}
      </div>
    </section>
  );
}
