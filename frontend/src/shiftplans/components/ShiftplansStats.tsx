import { type ReactNode } from "react";

import type { ShiftplansPlanViewProps } from "./planViewTypes";
import { fairnessRows } from "../shiftplanUtils";

/**
 * Render the fairness statistics panel.
 */
export function ShiftplansStats({ currentPlan }: Pick<ShiftplansPlanViewProps, "currentPlan">): ReactNode {
  const rows = currentPlan ? fairnessRows(currentPlan) : [];
  return (
    <details className="mt-5 no-print" id="sp-stats" hidden={!currentPlan}>
      <summary className="stat-label cursor-pointer select-none mb-2">Fairness-Statistik</summary>
      <div className="overflow-x-auto">
        <table className="table table-xs">
          <caption>Fairness-Statistik des aktuellen Schichtplans</caption>
          <thead>
            <tr>
              <th scope="col">Mitarbeiter</th>
              <th scope="col">Früh</th>
              <th scope="col">Spät</th>
              <th scope="col">Nacht</th>
              <th scope="col">Urlaub</th>
              <th scope="col">Stunden</th>
            </tr>
          </thead>
          <tbody id="sp-stats-body">
            {rows.map((row) => (
              <tr key={row.employee.id || row.employee.name}>
                <th scope="row">{row.employee.name || "-"}</th>
                <td>{row.frueh}</td>
                <td>{row.spaet}</td>
                <td>{row.nacht}</td>
                <td>{row.urlaub}</td>
                <td>{row.hours.toFixed(1)}h</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
