import { type ReactNode } from "react";

import {
  handoverDateLabel,
  handoverDateTimeLabel,
  machineName,
  machineStatusLabel,
  productionStatusLabel,
  shiftLabel,
} from "../handoverUtils";
import type { HandoverRecord } from "../handoverTypes";

type HandoverCardProps = {
  readonly handover: HandoverRecord;
  readonly onComplete: (handover: HandoverRecord) => void;
  readonly onEdit: (handover: HandoverRecord) => void;
  readonly writable: boolean;
};

/**
 * Render one compact handover metric.
 */
function Metric({ label, value }: { readonly label: string; readonly value: ReactNode }): ReactNode {
  return (
    <span>
      <small>{label}</small>
      <strong>{value || "-"}</strong>
    </span>
  );
}

/**
 * Render one optional handover detail block.
 */
function DetailBlock({
  label,
  value,
  variant,
}: {
  readonly label: string;
  readonly value?: string;
  readonly variant: string;
}): ReactNode {
  if (!value) return null;

  return (
    <section className={`handover-block ${variant}`}>
      <span>{label}</span>
      <p>{value}</p>
    </section>
  );
}

/**
 * Render one handover record card.
 */
export function HandoverCard({
  handover,
  onComplete,
  onEdit,
  writable,
}: HandoverCardProps): ReactNode {
  const completed = handover.status === "completed";
  const critical = Boolean(handover.safety_notes || handover.machine_status === "fault" || handover.production_status === "stopped");
  const cardClassName = [
    "handover-record-card",
    completed ? "is-completed" : "is-open",
    critical ? "is-critical" : "",
  ].filter(Boolean).join(" ");

  return (
    <article className={cardClassName}>
      <header className="handover-record-header">
        <div>
          <h3>{handoverDateLabel(handover.shift_date)} · {shiftLabel(handover.shift_type)}</h3>
          <p>
            {handover.department || "Bereich offen"}
            {handover.area ? ` · ${handover.area}` : ""}
            {machineName(handover) ? ` · ${machineName(handover)}` : ""}
          </p>
        </div>
        <div className="handover-record-badges">
          <span className={`badge status-badge ${completed ? "is-done" : "is-open"}`}>
            {completed ? "Bestätigt" : "Offen"}
          </span>
          {handover.problem_category ? (
            <span className="badge priority-badge is-normal">{handover.problem_category}</span>
          ) : null}
        </div>
      </header>
      <div className="handover-shift-flow" aria-label="Schichtfolge">
        <Metric label="Vorherige Schicht" value={shiftLabel(handover.previous_shift)} />
        <Metric label="Aktuelle Schicht" value={shiftLabel(handover.shift_type)} />
        <Metric label="Nächste Schicht" value={shiftLabel(handover.next_shift)} />
      </div>
      <div className="handover-record-metrics">
        <Metric label="Produktion" value={productionStatusLabel(handover.production_status)} />
        <Metric label="Maschine" value={machineStatusLabel(handover.machine_status)} />
        <Metric label="Dauer" value={`${Number(handover.duration_minutes || 0)} min`} />
        <Metric label="Verantwortlich" value={handover.responsible_employee || handover.handed_over_by || "-"} />
      </div>
      <div className="handover-record-blocks">
        <DetailBlock label="Schichtlage" value={handover.content} variant="is-status" />
        <DetailBlock label="Maschinenhinweis" value={handover.machine_notes} variant="is-machine" />
        <DetailBlock label="Ursache" value={handover.cause} variant="is-cause" />
        <DetailBlock label="Maßnahme" value={handover.action_taken} variant="is-action" />
        <DetailBlock label="Sicherheit" value={handover.safety_notes} variant="is-safety" />
        <DetailBlock label="Material / Ersatzteile" value={handover.material_notes} variant="is-material" />
        <DetailBlock label="Offene Tasks" value={handover.open_tasks} variant="is-open-items" />
        <DetailBlock label="Folgeaufgabe" value={handover.follow_up_task} variant="is-open-items" />
        <DetailBlock label="Nächste Schicht" value={handover.next_notes} variant="is-next" />
      </div>
      <footer className="handover-record-footer">
        <span>
          {handover.handed_over_at
            ? `Bestätigt am ${handoverDateTimeLabel(handover.handed_over_at)}`
            : "Noch nicht bestätigt"}
        </span>
        <div className="toolbar">
          {!completed && writable ? (
            <button className="btn btn-outline btn-sm" type="button" onClick={() => onEdit(handover)}>
              Bearbeiten
            </button>
          ) : null}
          {!completed && writable ? (
            <button className="btn btn-primary btn-sm" type="button" onClick={() => onComplete(handover)}>
              Bestätigen
            </button>
          ) : null}
        </div>
      </footer>
    </article>
  );
}
