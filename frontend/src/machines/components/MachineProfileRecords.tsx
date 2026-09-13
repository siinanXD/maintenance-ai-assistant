import type { ReactNode } from "react";

import type { MachineProfileRecord } from "../machineTypes";
import {
  criticalityBadgeClass,
  dateLabel,
  genericStatusBadgeClass,
  minutesLabel,
  priorityBadgeClass,
  priorityLabel,
  recordNumber,
  recordObject,
  recordString,
  statusBadgeClass,
  statusLabel,
  valueText
} from "../machineUtils";

type ProfileCardData = {
  readonly title: string;
  readonly subtitle?: string;
  readonly summary?: string;
  readonly badges?: ReadonlyArray<readonly [string, string]>;
  readonly metrics?: ReadonlyArray<readonly [string, string | number]>;
  readonly url?: string;
  readonly actionLabel?: string;
};

type ProfilePanelProps = {
  readonly selector: string;
  readonly kicker: string;
  readonly title: string;
  readonly actionHref?: string;
  readonly actionLabel?: string;
  readonly children: ReactNode;
};

/**
 * Render one machine profile panel shell.
 */
export function ProfilePanel({
  selector,
  kicker,
  title,
  actionHref,
  actionLabel,
  children
}: ProfilePanelProps): ReactNode {
  return (
    <article className="machine-profile-panel" {...{ [selector]: true }}>
      <div className="machine-profile-panel-header">
        <div>
          <p className="page-kicker">{kicker}</p>
          <h2>{title}</h2>
        </div>
        {actionHref ? <a className="btn btn-outline btn-sm" href={actionHref}>{actionLabel || "Öffnen"}</a> : null}
      </div>
      <div className="machine-profile-list">{children}</div>
    </article>
  );
}

/**
 * Render an empty profile panel state.
 */
function ProfileEmpty({ text, href, label }: { readonly text: string; readonly href?: string; readonly label?: string }): ReactNode {
  return (
    <div className="machine-profile-empty">
      <strong>{text}</strong>
      {href ? <a className="btn btn-outline btn-sm" href={href}>{label || "Öffnen"}</a> : null}
    </div>
  );
}

/**
 * Render one profile record card.
 */
function ProfileRecordCard({ data }: { readonly data: ProfileCardData }): ReactNode {
  return (
    <article className="machine-profile-record">
      <div className="machine-profile-record-header">
        <div>
          <h3>{data.title || "-"}</h3>
          <p>{data.subtitle || ""}</p>
        </div>
        <div className="machine-profile-record-badges">
          {(data.badges || []).map(([label, className]) => (
            <span className={className} key={`${label}-${className}`}>{label}</span>
          ))}
        </div>
      </div>
      {data.summary ? <p className="machine-profile-record-summary">{data.summary}</p> : null}
      {data.metrics?.length ? (
        <div className="machine-profile-record-metrics">
          {data.metrics.map(([label, value]) => (
            <span key={label}>
              <small>{label}</small>
              <strong>{valueText(value)}</strong>
            </span>
          ))}
        </div>
      ) : null}
      {data.url ? (
        <div className="machine-profile-record-actions">
          <a className="btn btn-outline btn-sm" href={data.url}>{data.actionLabel || "Öffnen"}</a>
        </div>
      ) : null}
    </article>
  );
}

/**
 * Render a list of profile records.
 */
export function ProfileRecordList({
  items,
  emptyText,
  mapper,
  emptyHref,
  emptyLabel
}: {
  readonly items: readonly MachineProfileRecord[] | undefined;
  readonly emptyText: string;
  readonly mapper: (record: MachineProfileRecord) => ProfileCardData;
  readonly emptyHref?: string;
  readonly emptyLabel?: string;
}): ReactNode {
  const rows = Array.isArray(items) ? items : [];
  if (!rows.length) {
    return <ProfileEmpty href={emptyHref} label={emptyLabel} text={emptyText} />;
  }

  return rows.map((item, index) => <ProfileRecordCard data={mapper(item)} key={`${mapper(item).title}-${index}`} />);
}

/**
 * Map a task record to a profile card.
 */
export function taskRecord(task: MachineProfileRecord): ProfileCardData {
  const department = recordObject(task, "department");
  const worker = recordObject(task, "current_worker");
  return {
    title: recordString(task, "title"),
    subtitle: typeof department?.name === "string" ? department.name : "Bereich offen",
    summary: recordString(task, "description") || "Keine Beschreibung hinterlegt.",
    badges: [
      [priorityLabel(task.priority), priorityBadgeClass(task.priority)],
      [statusLabel(task.status), statusBadgeClass(task.status)]
    ],
    metrics: [
      ["Fällig", dateLabel(task.due_date)],
      ["Zuordnung", typeof worker?.username === "string" ? worker.username : "Nicht gestartet"],
      ["Bezug", recordString(task, "machine_match") || "-"]
    ],
    url: recordString(task, "ui_url") || `/tasks?search=${encodeURIComponent(recordString(task, "title"))}`,
    actionLabel: "Aufgabe öffnen"
  };
}

/**
 * Map an error record to a profile card.
 */
export function errorRecord(error: MachineProfileRecord): ProfileCardData {
  return {
    title: [recordString(error, "error_code"), recordString(error, "title")].filter(Boolean).join(" · "),
    subtitle: recordString(error, "cause_category") || recordString(error, "machine") || "Störung",
    summary: recordString(error, "symptoms") || recordString(error, "description") || recordString(error, "solution") || "Keine Details hinterlegt.",
    badges: [
      [statusLabel(error.status), genericStatusBadgeClass(error.status)],
      [statusLabel(error.severity), criticalityBadgeClass(error.severity)]
    ],
    metrics: [
      ["Auswirkung", recordString(error, "impact") || "-"],
      ["Stillstand", minutesLabel(error.downtime_minutes)],
      ["Erfasst", dateLabel(error.created_at)]
    ],
    url: recordString(error, "ui_url") || `/errors?search=${encodeURIComponent(recordString(error, "error_code"))}`,
    actionLabel: "Störung öffnen"
  };
}

/**
 * Map a maintenance plan to a profile card.
 */
export function maintenanceRecord(plan: MachineProfileRecord): ProfileCardData {
  const department = recordObject(plan, "department");
  return {
    title: recordString(plan, "title"),
    subtitle: typeof department?.name === "string" ? department.name : "Wartungsplan",
    summary: recordString(plan, "description") || "Kein Ablauf hinterlegt.",
    badges: [
      [priorityLabel(plan.priority), priorityBadgeClass(plan.priority)],
      [plan.is_due ? "Fällig" : "Geplant", plan.is_due ? "badge badge-priority is-soon" : "badge badge-status is-progress"]
    ],
    metrics: [
      ["Intervall", `${recordNumber(plan, "interval_days")} Tage`],
      ["Nächster Termin", dateLabel(plan.next_due_date)],
      ["Letzte Erzeugung", dateLabel(plan.last_generated_at)]
    ],
    url: recordString(plan, "ui_url") || "/machines",
    actionLabel: "Wartungspläne"
  };
}

/**
 * Map a document or manual to a profile card.
 */
export function documentRecord(document: MachineProfileRecord, typeLabel: string): ProfileCardData {
  return {
    title: recordString(document, "title") || recordString(document, "original_filename") || typeLabel,
    subtitle: typeLabel,
    summary: recordString(document, "summary") || recordString(document, "analysis") || "Noch keine Zusammenfassung hinterlegt.",
    badges: [[recordString(document, "status") || recordString(document, "analysis_status") || "not_started", genericStatusBadgeClass(recordString(document, "status") || recordString(document, "analysis_status"))]],
    metrics: [
      ["Bereich", recordString(document, "department") || "-"],
      ["Version", recordString(document, "version") || "-"],
      ["Erstellt", dateLabel(document.created_at)]
    ],
    url: recordString(document, "ui_url") || "/documents",
    actionLabel: "Dokumente öffnen"
  };
}

/**
 * Map a shift handover to a profile card.
 */
export function handoverRecord(handover: MachineProfileRecord): ProfileCardData {
  return {
    title: `${dateLabel(handover.shift_date)} · ${valueText(handover.shift_type)}`,
    subtitle: recordString(handover, "area") || recordString(handover, "department") || "Schichtübergabe",
    summary: recordString(handover, "machine_status") || recordString(handover, "action_taken") || recordString(handover, "content") || "Keine Maschinennotiz hinterlegt.",
    badges: [[handover.status === "completed" ? "Bestätigt" : "Offen", genericStatusBadgeClass(handover.status)]],
    metrics: [
      ["Vorher", recordString(handover, "previous_shift") || "-"],
      ["Nächste", recordString(handover, "next_shift") || "-"],
      ["Verantwortlich", recordString(handover, "responsible_employee") || recordString(handover, "handed_over_by") || "-"]
    ],
    url: recordString(handover, "ui_url") || "/handover",
    actionLabel: "Übergabe öffnen"
  };
}

/**
 * Map inventory material to a profile card.
 */
export function materialRecord(material: MachineProfileRecord): ProfileCardData {
  return {
    title: recordString(material, "name"),
    subtitle: recordString(material, "manufacturer") || "Ersatzteil",
    summary: material.is_below_minimum ? "Mindestbestand unterschritten." : "Bestand im Profil hinterlegt.",
    badges: [[material.is_below_minimum ? "Prüfen" : "OK", material.is_below_minimum ? "badge badge-priority is-soon" : "badge badge-status is-done"]],
    metrics: [
      ["Bestand", recordNumber(material, "quantity")],
      ["Minimum", recordNumber(material, "min_quantity")],
      ["Wert", `${recordNumber(material, "total_value")} EUR`]
    ],
    url: "/inventory",
    actionLabel: "Lager öffnen"
  };
}

/**
 * Map timeline entry to a profile card.
 */
export function timelineRecord(item: MachineProfileRecord): ProfileCardData {
  return {
    title: recordString(item, "title"),
    subtitle: dateLabel(item.date),
    summary: recordString(item, "summary") || "Kein Kurztext hinterlegt.",
    badges: [[recordString(item, "label") || recordString(item, "type"), genericStatusBadgeClass(item.status)]],
    metrics: [
      ["Typ", recordString(item, "label") || recordString(item, "type")],
      ["Status", recordString(item, "status") || "-"]
    ],
    url: recordString(item, "ui_url"),
    actionLabel: "Quelle öffnen"
  };
}
