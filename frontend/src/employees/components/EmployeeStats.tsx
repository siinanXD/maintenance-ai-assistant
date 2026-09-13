import type { ReactNode } from "react";

import type { Employee } from "../employeeTypes";

type EmployeeStatsProps = {
  readonly employees: readonly Employee[];
};

/**
 * Headcount, departments and people with a machine qualification.
 */
export function EmployeeStats({ employees }: EmployeeStatsProps): ReactNode {
  const departments = new Set(employees.map((employee) => employee.department).filter(Boolean)).size;
  const qualified = employees.filter((employee) => Boolean(employee.qualifications?.trim())).length;

  return (
    <section className="surface-stat-grid ux-ops-summary-grid" aria-label="Personalstatus">
      <article className="surface-stat-card is-primary">
        <span>Mitarbeitende</span>
        <strong data-employee-count>{employees.length}</strong>
        <small>sichtbar für dich</small>
      </article>
      <article className="surface-stat-card is-neutral">
        <span>Abteilungen</span>
        <strong>{departments}</strong>
        <small>mit zugeordneten Personen</small>
      </article>
      <article className="surface-stat-card is-ai">
        <span>Qualifiziert</span>
        <strong>{qualified}</strong>
        <small>mit hinterlegten Qualifikationen</small>
      </article>
    </section>
  );
}
