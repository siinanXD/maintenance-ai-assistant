import { type ReactNode } from "react";

import { type DashboardKpiState } from "../dashboardModel";

/**
 * Render the four cockpit KPI cards.
 */
export function DashboardKpis({ kpis }: { readonly kpis: readonly DashboardKpiState[] }): ReactNode {
  return (
    <section className="executive-kpi-grid control-center-kpis" aria-label="Wichtige Kennzahlen">
      {kpis.map((kpi) => (
        <article className={`executive-kpi-card ${kpi.colorClass}`} key={kpi.label}>
          <span>{kpi.label}</span>
          <strong>{kpi.value}</strong>
          <small>{kpi.meta}</small>
          <div className="kpi-progress">
            <span style={{ width: kpi.progressWidth }} />
          </div>
        </article>
      ))}
    </section>
  );
}
