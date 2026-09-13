import type { ReactNode } from "react";

import type { Machine } from "../machineTypes";

type MachineStatsProps = {
  readonly machines: readonly Machine[];
};

/**
 * Machines, how many have open incidents, and the open work on them.
 */
export function MachineStats({ machines }: MachineStatsProps): ReactNode {
  const withIncidents = machines.filter((machine) => Number(machine.active_errors || 0) > 0).length;
  const openTasks = machines.reduce((sum, machine) => sum + Number(machine.open_tasks || 0), 0);

  return (
    <section className="surface-stat-grid ux-ops-summary-grid" aria-label="Maschinenstatus">
      <article className="surface-stat-card is-primary">
        <span>Anlagen</span>
        <strong data-machine-count>{machines.length}</strong>
        <small>mit Profil, Historie und QR-Etikett</small>
      </article>
      <article className="surface-stat-card is-warning">
        <span>Mit Störung</span>
        <strong data-dashboard-machine-issue-count>{withIncidents}</strong>
        <small>Anlagen mit offener Störung</small>
      </article>
      <article className="surface-stat-card is-neutral">
        <span>Offene Aufgaben</span>
        <strong>{openTasks}</strong>
        <small>an Anlagen gebunden</small>
      </article>
    </section>
  );
}
