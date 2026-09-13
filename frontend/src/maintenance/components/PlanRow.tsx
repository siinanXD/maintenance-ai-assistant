import { useState, type ReactNode } from "react";

import { DUE_STATE_LABELS, RESULT_LABELS, daysUntil, formatPlanDate, intervalLabel } from "../maintenanceLabels";
import { loadRecords } from "../maintenanceApi";
import type { MaintenancePlan, MaintenanceRecord } from "../maintenanceTypes";

type PlanRowProps = {
  readonly plan: MaintenancePlan;
  readonly writable: boolean;
  readonly onEdit: (plan: MaintenancePlan) => void;
  readonly onRecord: (plan: MaintenancePlan) => void;
};

/**
 * Return the relative due text, e.g. "seit 3 Tagen" or "in 12 Tagen".
 */
function relativeDue(plan: MaintenancePlan): string {
  const days = daysUntil(plan.next_due_date);
  if (days === 0) return "heute";
  if (days < 0) return days === -1 ? "seit 1 Tag" : `seit ${-days} Tagen`;
  return days === 1 ? "morgen" : `in ${days} Tagen`;
}

/**
 * One plan with due date, last proof and actions; history opens inline.
 */
export function PlanRow({ plan, writable, onEdit, onRecord }: PlanRowProps): ReactNode {
  const [records, setRecords] = useState<MaintenanceRecord[] | null>(null);

  return (
    <li className={`plan-row is-${plan.due_state}`}>
      <div className="plan-row-due">
        <strong>{formatPlanDate(plan.next_due_date)}</strong>
        <small>{plan.is_active ? relativeDue(plan) : DUE_STATE_LABELS.inactive}</small>
      </div>
      <div className="plan-row-main">
        <div className="plan-row-title">
          <span className={`plan-kind is-${plan.kind}`}>{plan.kind === "inspection" ? "Prüfpflicht" : "Wartung"}</span>
          <h3>{plan.title}</h3>
        </div>
        <p className="plan-row-meta">
          {[plan.machine?.name || "Ohne Maschine", intervalLabel(plan.interval_days), plan.legal_basis, plan.department?.name].filter(Boolean).join(" · ")}
        </p>
        <p className="plan-row-last">
          {plan.last_record
            ? <>Zuletzt {formatPlanDate(plan.last_record.performed_on)} von {plan.last_record.performed_by}: <span className={`plan-result is-${plan.last_record.result}`}>{RESULT_LABELS[plan.last_record.result]}</span></>
            : "Noch kein Nachweis dokumentiert."}
        </p>
        <details
          className="attachment-panel"
          onToggle={(event) => {
            if (event.currentTarget.open && records === null) void loadRecords(plan.id).then(setRecords).catch(() => setRecords([]));
          }}
        >
          <summary>Nachweise</summary>
          <div className="attachment-body">
            {records === null ? <p className="panel-meta">Wird geladen…</p> : null}
            {records && !records.length ? <p className="panel-meta">Noch keine Nachweise.</p> : null}
            {records && records.length ? (
              <ol className="plan-history">
                {records.map((record) => (
                  <li key={record.id}>
                    <span className="plan-history-date">{formatPlanDate(record.performed_on)}</span>
                    <span className={`plan-result is-${record.result}`}>{RESULT_LABELS[record.result]}</span>
                    <span>{record.performed_by}{record.notes ? ` – ${record.notes}` : ""}</span>
                    {record.follow_up_task_id ? <a href={`/tasks?search=${encodeURIComponent("Mängel beheben")}`}>Aufgabe</a> : null}
                  </li>
                ))}
              </ol>
            ) : null}
          </div>
        </details>
      </div>
      {writable ? (
        <div className="plan-row-actions">
          <button className="btn btn-primary btn-sm" type="button" onClick={() => onRecord(plan)}>Durchgeführt</button>
          <button className="btn btn-ghost btn-sm" type="button" onClick={() => onEdit(plan)}>Bearbeiten</button>
        </div>
      ) : null}
    </li>
  );
}
