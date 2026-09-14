import { type ReactNode } from "react";

import type { ShiftplansPlanViewProps } from "./planViewTypes";

/**
 * Render warning, changelog, and deletion shells.
 */
export function ShiftplansAdminDetails({
  changelog,
  currentPlan,
  isAdmin,
  onDeletePlan,
  warnings,
}: Pick<ShiftplansPlanViewProps, "changelog" | "currentPlan" | "isAdmin" | "onDeletePlan" | "warnings">): ReactNode {
  return (
    <>
      <details className="mt-4 no-print" id="sp-warnings" hidden={!warnings.length}>
        <summary className="stat-label cursor-pointer select-none mb-2" id="sp-warn-summary">
          Warnungen anzeigen ({warnings.length})
        </summary>
        <ul id="sp-warn-list" className="space-y-1 mt-2" role="list">
          {warnings.map((warning, index) => (
            <li className={`panel-meta ${warning.severity === "critical" ? "text-error" : "text-warning"}`} key={`${warning.message}-${index}`}>
              {warning.severity === "critical" ? "Kritisch: " : "Warnung: "}
              {warning.message}
            </li>
          ))}
        </ul>
      </details>
      <details className="mt-5 no-print" id="sp-changelog" hidden={!isAdmin || !currentPlan?.id}>
        <summary className="stat-label cursor-pointer select-none mb-2">Änderungsprotokoll</summary>
        <div className="overflow-x-auto">
          <table className="table table-xs">
            <caption>Änderungsprotokoll des aktuellen Schichtplans</caption>
            <thead>
              <tr>
                <th scope="col">Zeitpunkt</th>
                <th scope="col">Benutzer</th>
                <th scope="col">Aktion</th>
                <th scope="col">Feld</th>
                <th scope="col">Alt</th>
                <th scope="col">Neu</th>
              </tr>
            </thead>
            <tbody id="sp-changelog-body">
              {changelog.map((log, index) => (
                <tr key={`${log.changed_at}-${index}`}>
                  <td>{log.changed_at ? new Date(log.changed_at).toLocaleString("de-DE") : "-"}</td>
                  <td>{log.user || "-"}</td>
                  <td>{log.action || "-"}</td>
                  <td>{log.field_name || "-"}</td>
                  <td>{log.old_value || "-"}</td>
                  <td>{log.new_value || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <div className="toolbar mt-5 no-print" id="sp-delete-wrap" hidden={!isAdmin || !currentPlan?.id}>
        <button className="btn btn-error btn-sm" id="sp-delete-btn" type="button" onClick={onDeletePlan}>
          Plan löschen
        </button>
      </div>
    </>
  );
}
