import type { ReactNode } from "react";

import type { VacationSummary } from "../vacationTypes";
import { vacationSummaryMeta } from "../vacationUtils";
import { VacationMetric } from "./VacationCards";

type VacationSummaryPanelProps = {
  readonly summaries: readonly VacationSummary[];
};

/**
 * Render vacation balances per employee.
 */
export function VacationSummaryPanel(props: VacationSummaryPanelProps): ReactNode {
  return (
    <article className="vacation-summary-panel app-card">
      <header className="vacation-panel-header">
        <div>
          <p className="section-kicker">Kontingente</p>
          <h2>Resturlaub je Mitarbeiter</h2>
          <p>Verfügbar, reserviert und genehmigt mit Bereich, Schicht und Qualifikation.</p>
        </div>
      </header>
      <div className="vacation-summary-list">
        {props.summaries.length ? props.summaries.map((summary) => {
          const available = Number(summary.available || 0);
          const className = `vacation-summary-card${available <= 0 ? " is-critical" : available <= 5 || Number(summary.pending || 0) >= 5 ? " is-warning" : ""}`;
          return (
            <article className={className} key={summary.employee_id}>
              <header>
                <h3>{summary.name || "-"}</h3>
                <p>{vacationSummaryMeta(summary)}</p>
              </header>
              <div className="vacation-summary-numbers">
                <VacationMetric label="Verfügbar" value={String(summary.available || 0)} />
                <VacationMetric label="Reserviert" value={String(summary.pending || 0)} />
                <VacationMetric label="Genehmigt" value={String(summary.used || 0)} />
                <VacationMetric label="Gesamt" value={String(summary.total || 0)} />
              </div>
              <p className="vacation-card-meta">{summary.qualifications ? `Qualifikation: ${summary.qualifications}` : "Qualifikation nicht hinterlegt"}</p>
            </article>
          );
        }) : <p className="empty-state">Wird geladen...</p>}
      </div>
    </article>
  );
}
