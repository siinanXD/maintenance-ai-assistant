import { type ReactNode } from "react";

import type { AiSummary, AuditEntry, BackupEntry, MessageState } from "../adminUserTypes";
import { adminDateLabel, compactNumber, formatBytes, formatUsd, percentLabel } from "../adminUserUtils";

type AuditLogPanelProps = {
  readonly auditEntries: readonly AuditEntry[];
  readonly auditSearch: string;
  readonly onAuditRefresh: () => Promise<void>;
  readonly onAuditSearch: (value: string) => void;
};

/**
 * Render the audit log panel.
 */
export function AuditLogPanel(props: AuditLogPanelProps): ReactNode {
  return (
    <article className="card app-card mobile-secondary-card lg:col-span-6">
      <div className="card-body">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Audit-Log</h2>
            <p className="panel-meta">Sicherheitskritische Admin-Änderungen</p>
          </div>
          <button className="btn btn-outline btn-sm" type="button" onClick={() => void props.onAuditRefresh()}>Aktualisieren</button>
        </div>
        <div className="toolbar mb-4">
          <input className="input input-bordered w-full" type="search" placeholder="Aktion, Ressource oder Nutzer suchen..." autoComplete="off" value={props.auditSearch} onChange={(event) => props.onAuditSearch(event.currentTarget.value)} />
        </div>
        <div className="table-wrap">
          <table className="table data-table">
            <caption>Audit-Log sicherheitskritischer Admin-Aktionen</caption>
            <thead>
              <tr>
                <th scope="col">Zeit</th>
                <th scope="col">Aktion</th>
                <th scope="col">Ressource</th>
                <th scope="col">Akteur</th>
              </tr>
            </thead>
            <tbody>
              {props.auditEntries.length ? props.auditEntries.map((entry, index) => (
                <tr key={`${entry.action}-${entry.created_at}-${index}`}>
                  <td>{adminDateLabel(entry.created_at)}</td>
                  <td>{entry.action || "-"}</td>
                  <td>{entry.resource_type}{entry.resource_id ? ` #${entry.resource_id}` : ""}</td>
                  <td>{entry.actor?.username || "-"}</td>
                </tr>
              )) : <tr><td colSpan={4}>Keine Audit-Einträge vorhanden.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </article>
  );
}

type BackupPanelProps = {
  readonly backups: readonly BackupEntry[];
  readonly message: MessageState;
  readonly onCreate: () => Promise<void>;
  readonly onDownload: (backup: BackupEntry) => boolean;
  readonly onRestore: (backup: BackupEntry) => Promise<void>;
};

/**
 * Render the backup management panel.
 */
export function BackupPanel(props: BackupPanelProps): ReactNode {
  return (
    <article className="card app-card mobile-secondary-card lg:col-span-6">
      <div className="card-body">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Backups</h2>
            <p className="panel-meta">Datenbank, Uploads, Dokumente und Logs</p>
          </div>
          <button className="btn btn-primary btn-sm" type="button" onClick={() => void props.onCreate()}>Backup erstellen</button>
        </div>
        <p className={`panel-meta mb-3${props.message.error ? " is-error" : ""}`}>{props.message.text}</p>
        <div className="table-wrap">
          <table className="table data-table">
            <caption>Erstellte Backups mit Größe, Zeitpunkt und Aktionen</caption>
            <thead>
              <tr>
                <th scope="col">Datei</th>
                <th scope="col">Größe</th>
                <th scope="col">Zeit</th>
                <th scope="col">Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {props.backups.length ? props.backups.map((backup) => (
                <tr key={backup.id}>
                  <td>{backup.filename}</td>
                  <td>{formatBytes(backup.size_bytes)}</td>
                  <td>{adminDateLabel(backup.created_at)}</td>
                  <td>
                    <div className="table-actions">
                      <button className="btn btn-outline btn-sm" type="button" onClick={() => props.onDownload(backup)}>Download</button>
                      <button className="btn btn-outline btn-sm" type="button" onClick={() => void props.onRestore(backup)}>Restore</button>
                    </div>
                  </td>
                </tr>
              )) : <tr><td colSpan={4}>Noch keine Backups vorhanden.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </article>
  );
}

type AiAnalyticsPanelProps = {
  readonly latestEvents: readonly NonNullable<AiSummary["latest_events"]>[number][];
  readonly summary: AiSummary;
  readonly userMetrics: readonly NonNullable<AiSummary["user_metrics"]>[number][];
};

/**
 * Render AI analytics for the admin users page.
 */
export function AiAnalyticsPanel(props: AiAnalyticsPanelProps): ReactNode {
  const helpfulRate = props.summary.feedback?.helpful_rate;
  return (
    <article className="card app-card mobile-secondary-card lg:col-span-12">
      <div className="card-body">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">AI-Auswertung</h2>
            <p className="panel-meta">Nutzung, Fallbacks und Feedback der letzten 7 Tage</p>
          </div>
          <span className="badge badge-ai">AI</span>
        </div>
        <div className="dashboard-kpi-grid">
          <Kpi label="Events" meta="AI-Workflows" value={String(props.summary.events_total || 0)} />
          <Kpi label="Fallbacks" meta="lokal beantwortet" value={String(props.summary.fallback_count || 0)} />
          <Kpi label="Feedback" meta="hilfreich Quote" value={helpfulRate === null || helpfulRate === undefined ? "-" : `${Math.round(helpfulRate * 100)}%`} />
          <Kpi label="Nicht hilfreich" meta="Feedback" value={String(props.summary.feedback?.not_helpful || 0)} />
          <Kpi label="Ø Latenz" meta="Millisekunden" value={String(props.summary.average_latency_ms || 0)} />
          <Kpi label="Tokens" meta="gesamt" value={compactNumber(props.summary.total_tokens || 0)} />
          <Kpi label="Kosten" meta={props.summary.price_configuration?.configured ? "geschätzt" : props.summary.price_configuration?.message || "Kosten nicht konfiguriert"} value={formatUsd(props.summary.estimated_cost_usd || 0)} />
        </div>
        <div className="table-wrap mt-4">
          <table className="table data-table">
            <caption>AI-Kosten nach Nutzer mit Langfuse User-ID</caption>
            <thead>
              <tr>
                <th scope="col">Nutzer</th>
                <th scope="col">Langfuse User</th>
                <th scope="col">Events</th>
                <th scope="col">Tokens</th>
                <th scope="col">Kosten</th>
                <th scope="col">Fallback</th>
                <th scope="col">Letzte Nutzung</th>
              </tr>
            </thead>
            <tbody>
              {props.userMetrics.length ? props.userMetrics.map((item, index) => (
                <tr key={`${item.username}-${index}`}>
                  <td>{item.username || "Unbekannt"}</td>
                  <td>{item.langfuse_user_id || "-"}</td>
                  <td>{String(item.events || 0)}</td>
                  <td>{compactNumber(item.total_tokens || 0)}</td>
                  <td>{formatUsd(item.estimated_cost_usd || 0)}</td>
                  <td>{percentLabel(item.fallback_rate || 0)}</td>
                  <td>{item.latest_used_at ? adminDateLabel(item.latest_used_at) : "-"}</td>
                </tr>
              )) : <tr><td colSpan={7}>Noch keine nutzerbezogenen AI-Kosten vorhanden.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="grid gap-4 md:grid-cols-2 mt-4">
          <MetricList emptyText="Keine Workflows" title="Häufige Workflows" values={props.summary.workflow_counts} />
          <MetricList emptyText="Keine Fehler" title="Letzte Fehlerkategorien" values={props.summary.error_counts} />
        </div>
        <div className="table-wrap mt-4">
          <table className="table data-table">
            <caption>Letzte AI-Events in der Nutzerverwaltung</caption>
            <thead>
              <tr>
                <th scope="col">Workflow</th>
                <th scope="col">Status</th>
                <th scope="col">Modell</th>
                <th scope="col">Quellen</th>
                <th scope="col">Latenz</th>
                <th scope="col">Fallback</th>
                <th scope="col">Zeit</th>
              </tr>
            </thead>
            <tbody>
              {props.latestEvents.length ? props.latestEvents.map((event, index) => (
                <tr key={`${event.workflow}-${event.created_at}-${index}`}>
                  <td>{event.workflow}</td>
                  <td>{event.status}</td>
                  <td>{event.model || "-"}</td>
                  <td>{String(event.source_count || 0)}</td>
                  <td>{String(event.latency_ms || 0)} ms</td>
                  <td>{event.fallback_used ? "ja" : "nein"}</td>
                  <td>{adminDateLabel(event.created_at)}</td>
                </tr>
              )) : <tr><td colSpan={7}>Noch keine AI-Events vorhanden.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </article>
  );
}

/**
 * Render one KPI card.
 */
function Kpi(props: { readonly label: string; readonly meta: string; readonly value: string }): ReactNode {
  return (
    <article className="kpi-card">
      <span className="kpi-label">{props.label}</span>
      <strong className="kpi-value">{props.value}</strong>
      <span className="kpi-meta">{props.meta}</span>
    </article>
  );
}

/**
 * Render a compact metric list.
 */
function MetricList(props: { readonly emptyText: string; readonly title: string; readonly values?: Record<string, number> }): ReactNode {
  const entries = Object.entries(props.values || {}).sort((left, right) => right[1] - left[1]).slice(0, 5);
  return (
    <div className="surface-panel">
      <h3 className="panel-title text-base">{props.title}</h3>
      <div className="stacked-list">
        {entries.length ? entries.map(([label, count]) => (
          <div className="stacked-list-row" key={label}>
            <span>{label || "-"}</span>
            <strong>{String(count)}</strong>
          </div>
        )) : <div className="panel-meta">{props.emptyText}</div>}
      </div>
    </div>
  );
}
