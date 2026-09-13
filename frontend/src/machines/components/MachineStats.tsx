import type { ReactNode } from "react";

import type { Machine } from "../machineTypes";

type MachineStatsProps = {
  readonly machines: readonly Machine[];
  readonly issueCount: number;
};

/**
 * Render machine overview KPI cards.
 */
export function MachineStats({ machines, issueCount }: MachineStatsProps): ReactNode {
  return (
    <section className="surface-stat-grid ux-ops-summary-grid" aria-label="Maschinenstatus">
      <article className="surface-stat-card is-primary">
        <span>Anlagen</span>
        <strong data-machine-count>{machines.length} Maschinen</strong>
        <small>Alle Produktionsanlagen mit Profil, Historie und Status.</small>
      </article>
      <article className="surface-stat-card is-warning">
        <span>Störungen</span>
        <strong data-dashboard-machine-issue-count>{issueCount}</strong>
        <small>Offene Störungen mit Maschinenbezug.</small>
      </article>
      <article className="surface-stat-card is-ai">
        <span>Wartung</span>
        <strong>Präventiv</strong>
        <small>Hinweise aus Aufgaben, Fehlerhistorie und Anlagenakte.</small>
      </article>
      <article className="surface-stat-card is-neutral">
        <span>Profile</span>
        <strong>Detailansicht</strong>
        <small>Offene Tasks, Dokumente und Übergaben je Maschine.</small>
      </article>
    </section>
  );
}
