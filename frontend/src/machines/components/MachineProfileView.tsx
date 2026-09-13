import type { ReactNode } from "react";

import type { MachineProfile, MachineProfileRecord } from "../machineTypes";
import {
  criticalityBadgeClass,
  criticalityLabel,
  dateLabel,
  genericStatusBadgeClass,
  machineStatusLabel,
  minutesLabel,
  valueText
} from "../machineUtils";
import {
  ProfilePanel,
  ProfileRecordList,
  documentRecord,
  errorRecord,
  handoverRecord,
  maintenanceRecord,
  materialRecord,
  taskRecord,
  timelineRecord
} from "./MachineProfileRecords";
import { MachineQrLabel } from "./MachineQrLabel";

type MachineProfileViewProps = {
  readonly message: string;
  readonly profile: MachineProfile | null;
};

/**
 * Render fact rows for the profile sidebar.
 */
function FactGrid({ profile }: { readonly profile: MachineProfile | null }): ReactNode {
  const machine = profile?.machine;
  return (
    <div className="machine-profile-facts">
      {[
        ["Status", machineStatusLabel(machine?.status)],
        ["Kritikalität", criticalityLabel(machine?.criticality)],
        ["Produkt", machine?.produced_item || "-"],
        ["Personalbedarf", `${machine?.required_employees || 1} MA`],
        ["Werk", machine?.site?.name || "-"],
        ["Angelegt", dateLabel(machine?.created_at)]
      ].map(([label, value]) => (
        <span key={label}>
          <small>{label}</small>
          <strong>{value}</strong>
        </span>
      ))}
    </div>
  );
}

/**
 * Render machine profile KPI cards.
 */
function ProfileKpis({ profile }: { readonly profile: MachineProfile | null }): ReactNode {
  const kpis = profile?.kpis || {};
  const kpiRows: ReadonlyArray<readonly [string, unknown, string, string]> = [
    ["Verfügbarkeit", kpis.availability_percent == null ? "–" : `${String(kpis.availability_percent).replace(".", ",")} %`, "Letzte 90 Tage", "is-work"],
    ["MTBF", kpis.mtbf_hours == null ? "keine Ausfälle" : `${Math.round(Number(kpis.mtbf_hours))} h`, `${kpis.failure_count || 0} Ausfälle in 90 Tagen`, "is-maintenance"],
    ["MTTR", kpis.mttr_minutes == null ? "–" : minutesLabel(kpis.mttr_minutes), "Mittlere Reparaturzeit", "is-downtime"],
    ["Aktive Störungen", kpis.active_errors || 0, `${kpis.critical_errors || 0} davon kritisch`, "is-risk"],
    ["Offene Aufgaben", kpis.open_tasks || 0, "Aktive Arbeit zur Maschine", "is-critical"],
    ["Pläne fällig", kpis.maintenance_due || 0, "Prüfungen und Wartungen", "is-knowledge"]
  ];

  return (
    <section className="machine-profile-kpi-grid" aria-label="Wichtige Maschinenkennzahlen" data-machine-profile-kpis>
      {kpiRows.map(([label, value, meta, tone]) => (
        <article className={`machine-profile-kpi-card ${tone}`} key={label}>
          <span>{label}</span>
          <strong>{valueText(value)}</strong>
          <small>{meta}</small>
        </article>
      ))}
    </section>
  );
}

/**
 * Render the full machine profile page.
 */
export function MachineProfileView({ message, profile }: MachineProfileViewProps): ReactNode {
  const machine = profile?.machine;
  const query = encodeURIComponent(machine?.name || "");
  const permissions = profile?.permissions || {};
  const reports = profile?.documents?.reports || [];
  const manuals = profile?.documents?.manuals || [];
  const documentRows = [
    ...reports.map((item) => ({ item, type: "Bericht" })),
    ...manuals.map((item) => ({ item, type: "Handbuch" }))
  ] as readonly { readonly item: MachineProfileRecord; readonly type: string }[];

  return (
    <section className="machine-profile-page" data-machine-profile-page data-machine-id={machine?.id || ""}>
      <section className="machine-profile-hero app-card">
        <div className="machine-profile-copy">
          <p className="page-kicker">Maschinenprofil</p>
          <h1 className="page-title" data-machine-profile-name>{machine?.name || "Maschine wird geladen"}</h1>
          <p className="page-description" data-machine-profile-summary>
            {machine?.name
              ? [machine.produced_item || "Kein Produkt hinterlegt", `${machine.required_employees || 1} Mitarbeiter pro Schicht`, machine.site?.name || "Werk nicht zugeordnet"].join(" · ")
              : "Stammdaten, offene Arbeit, Störungen, Dokumente und Übergaben an einem Ort."}
          </p>
          <div className="machine-profile-badges" data-machine-profile-badges>
            <span className={genericStatusBadgeClass(machine?.status)}>{machineStatusLabel(machine?.status)}</span>
            <span className={criticalityBadgeClass(machine?.criticality)}>{criticalityLabel(machine?.criticality)}</span>
          </div>
        </div>
        <div className="machine-profile-actions">
          <a className="btn btn-primary btn-sm" data-machine-profile-report-link href={`/errors?machine=${query}#incident-create`}>Störung melden</a>
          <a className="btn btn-outline btn-sm" data-machine-profile-task-link href={`/tasks?search=${query}`}>Aufgabe planen</a>
          <a className="btn btn-outline btn-sm" data-machine-profile-error-link href={`/errors?search=${query}`}>Störungen prüfen</a>
          <a className="btn btn-outline btn-sm" data-machine-profile-document-link href={`/documents?search=${query}`}>Dokumente</a>
          {machine?.id ? <MachineQrLabel machineId={machine.id} machineName={machine.name || "Maschine"} /> : null}
        </div>
      </section>

      <p className="workflow-status" role="status" aria-live="polite" data-machine-profile-message>{message}</p>
      <ProfileKpis profile={profile} />

      <section className="machine-profile-layout">
        <aside className="machine-profile-side">
          <article className="machine-profile-panel" data-machine-profile-master>
            <div className="machine-profile-panel-header">
              <div>
                <p className="page-kicker">Stammdaten</p>
                <h2>Maschine</h2>
              </div>
            </div>
            <FactGrid profile={profile} />
          </article>
          <ProfilePanel selector="data-machine-profile-materials" kicker="Material" title="Ersatzteile">
            {permissions.inventory === false ? (
              <div className="machine-profile-empty"><strong>Keine Berechtigung für diesen Bereich.</strong></div>
            ) : (
              <ProfileRecordList emptyHref="/inventory" emptyLabel="Lager öffnen" emptyText="Keine Ersatzteile zugeordnet." items={profile?.materials} mapper={materialRecord} />
            )}
          </ProfilePanel>
          <ProfilePanel selector="data-machine-profile-timeline" kicker="Verlauf" title="Letzte Signale">
            <ProfileRecordList emptyText="Noch keine Signale im Maschinenverlauf." items={profile?.timeline} mapper={timelineRecord} />
          </ProfilePanel>
        </aside>

        <div className="machine-profile-main">
          <ProfilePanel selector="data-machine-profile-tasks" kicker="Arbeit" title="Offene Aufgaben" actionHref="/tasks" actionLabel="Alle Aufgaben">
            {permissions.tasks === false ? <div className="machine-profile-empty"><strong>Keine Berechtigung für diesen Bereich.</strong></div> : <ProfileRecordList emptyHref="/tasks" emptyLabel="Aufgabe anlegen" emptyText="Keine offenen Aufgaben zur Maschine." items={profile?.open_tasks} mapper={taskRecord} />}
          </ProfilePanel>
          <ProfilePanel selector="data-machine-profile-errors" kicker="Lage" title="Aktive Störungen" actionHref="/errors" actionLabel="Fehlerkatalog">
            {permissions.errors === false ? <div className="machine-profile-empty"><strong>Keine Berechtigung für diesen Bereich.</strong></div> : <ProfileRecordList emptyHref="/errors" emptyLabel="Störung melden" emptyText="Keine aktive Störung zur Maschine." items={profile?.active_errors} mapper={errorRecord} />}
          </ProfilePanel>
          <ProfilePanel selector="data-machine-profile-error-history" kicker="Historie" title="Fehlerhistorie">
            {permissions.errors === false ? <div className="machine-profile-empty"><strong>Keine Berechtigung für diesen Bereich.</strong></div> : <ProfileRecordList emptyText="Noch keine Fehlerhistorie vorhanden." items={profile?.error_history} mapper={errorRecord} />}
          </ProfilePanel>
          <ProfilePanel selector="data-machine-profile-maintenance" kicker="Wartung" title="Prüfungen und Wartungen" actionHref="/maintenance" actionLabel="Alle Pläne">
            <ProfileRecordList emptyHref="/maintenance" emptyLabel="Plan anlegen" emptyText="Keine Wartungspläne für diese Maschine." items={profile?.maintenance_plans} mapper={maintenanceRecord} />
          </ProfilePanel>
          <ProfilePanel selector="data-machine-profile-documents" kicker="Wissen" title="Dokumente und Handbücher" actionHref="/documents" actionLabel="Knowledge Base">
            {permissions.documents === false ? <div className="machine-profile-empty"><strong>Keine Berechtigung für diesen Bereich.</strong></div> : <ProfileRecordList emptyHref="/documents" emptyLabel="Dokument hochladen" emptyText="Keine Dokumente oder Handbücher zugeordnet." items={documentRows.map((entry) => entry.item)} mapper={(item) => documentRecord(item, documentRows.find((entry) => entry.item === item)?.type || "Dokument")} />}
          </ProfilePanel>
          <ProfilePanel selector="data-machine-profile-handovers" kicker="Schicht" title="Übergaben zur Maschine" actionHref="/handover" actionLabel="Schichtübergabe">
            {permissions.shiftplans === false ? <div className="machine-profile-empty"><strong>Keine Berechtigung für diesen Bereich.</strong></div> : <ProfileRecordList emptyHref="/handover" emptyLabel="Übergabe erfassen" emptyText="Keine Übergaben zur Maschine." items={profile?.shift_handovers} mapper={handoverRecord} />}
          </ProfilePanel>
        </div>
      </section>
    </section>
  );
}
