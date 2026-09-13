import { type ReactNode } from "react";

import { canViewDashboard } from "../../auth/permissions";
import { type DashboardViewState } from "../dashboardModel";
import {
  aiSystemRows,
  dashboardSignalClass,
  knowledgeRows,
  prioritySignals,
  riskRows,
  technicalIndexRows,
  type DashboardSignalItem,
  type DashboardStatusRow,
  warningSignals
} from "../dashboardTechnicalModel";

type DashboardTechnicalDetailsProps = {
  readonly dashboardState: DashboardViewState;
};

type TechnicalSignalCardProps = {
  readonly action?: ReactNode;
  readonly className: string;
  readonly contentClassName: string;
  readonly description: string;
  readonly title: string;
  readonly children: ReactNode;
};

/**
 * Render one signal card item with the existing dashboard classes.
 */
function SignalItem({ item }: { readonly item: DashboardSignalItem }): ReactNode {
  const className = `ai-signal-card ${dashboardSignalClass(item.severity)}`;
  const marker = item.severity === "critical" || item.severity === "warning" ? "!" : "OK";
  const content = (
    <>
      <span className="ai-signal-marker">{marker}</span>
      <div>
        <strong>{item.label}</strong>
        <small>{item.detail}</small>
      </div>
      <span>{item.value}</span>
    </>
  );

  if (item.href) {
    return (
      <a className={className} href={item.href}>
        {content}
      </a>
    );
  }

  return <article className={className}>{content}</article>;
}

/**
 * Render one status row.
 */
function StatusRow({ row }: { readonly row: DashboardStatusRow }): ReactNode {
  return (
    <div className={`ai-system-row ${dashboardSignalClass(row.severity)}`}>
      <span>{row.label}</span>
      <strong>{row.value}</strong>
      <small>{row.detail}</small>
    </div>
  );
}

/**
 * Render one warning feed item.
 */
function WarningItem({ item }: { readonly item: DashboardSignalItem }): ReactNode {
  const marker = item.label.slice(0, 2).toUpperCase();
  const content = (
    <>
      <span className="activity-feed-marker">{marker}</span>
      <div>
        <strong>{item.label}</strong>
        <small>{item.detail}</small>
      </div>
    </>
  );

  if (item.href) {
    return (
      <a className={`activity-feed-item ${dashboardSignalClass(item.severity)}`} href={item.href}>
        {content}
      </a>
    );
  }

  return <div className={`activity-feed-item ${dashboardSignalClass(item.severity)}`}>{content}</div>;
}

/**
 * Render an empty state when a technical section has no active rows.
 */
function EmptyState({ children }: { readonly children: ReactNode }): ReactNode {
  return <div className="empty-state">{children}</div>;
}

/**
 * Render one AI signal panel.
 */
function TechnicalSignalCard({
  action,
  children,
  className,
  contentClassName,
  description,
  title
}: TechnicalSignalCardProps): ReactNode {
  return (
    <article className={`ops-panel app-card ${className}`}>
      <header className="ops-panel-header">
        <div>
          <h2>{title}</h2>
          <p className="panel-meta">{description}</p>
        </div>
        {action}
      </header>
      <div className={contentClassName}>
        {children}
      </div>
    </article>
  );
}

/**
 * Render signal items or an empty state.
 */
function SignalList({ emptyText, signals }: { readonly emptyText: string; readonly signals: readonly DashboardSignalItem[] }): ReactNode {
  if (!signals.length) {
    return <EmptyState>{emptyText}</EmptyState>;
  }

  return signals.map((item) => <SignalItem item={item} key={`${item.label}-${item.value}`} />);
}

/**
 * Render status rows or an empty state.
 */
function StatusRows({ emptyText, rows }: { readonly emptyText: string; readonly rows: readonly DashboardStatusRow[] }): ReactNode {
  if (!rows.length) {
    return <EmptyState>{emptyText}</EmptyState>;
  }

  return rows.map((row) => <StatusRow key={row.label} row={row} />);
}

/**
 * Render the collapsible technical dashboard status area.
 */
export function DashboardTechnicalDetails({ dashboardState }: DashboardTechnicalDetailsProps): ReactNode {
  const { data } = dashboardState;
  const priorityItems = prioritySignals(data);
  const aiRows = aiSystemRows(data);
  const riskItems = riskRows(data);
  const knowledgeItems = knowledgeRows(data);
  const warnings = warningSignals(data);
  const indexRows = technicalIndexRows(data);

  return (
    <details className="section-disclosure control-center-technical">
      <summary>
        <span>
          <strong>Technische Details und Quellenstatus</strong>
          <small>AI-, Index- und Admin-Signale bleiben sichtbar, dominieren aber nicht die operative Lage.</small>
        </span>
      </summary>
      <section className="ai-ops-command-grid" aria-label="AI Operations Signale">
        <TechnicalSignalCard
          className="ai-priority-panel"
          contentClassName="ai-priority-rail"
          description="Kritische Fehler, Sicherheit, Gaps und Quellenrisiken."
          title="Prioritätslage"
        >
          <SignalList emptyText="Keine kritischen Operations-Signale im aktuellen Datenfenster." signals={priorityItems} />
        </TechnicalSignalCard>
        <TechnicalSignalCard
          action={(
            <a hidden={!canViewDashboard("admin_ai")} href="/admin/ai">
              Details
            </a>
          )}
          className="ai-system-panel"
          contentClassName="ai-system-rail"
          description="Nur-Lese Betriebszustand ohne Promptinhalte."
          title="AI Systemstatus"
        >
          <StatusRows emptyText="Systemstatus wird geladen." rows={aiRows} />
        </TechnicalSignalCard>
        <TechnicalSignalCard
          className="ai-risk-panel"
          contentClassName="ai-risk-grid"
          description="Sicherheit, Fallbacks und Feedback."
          title="AI Risk Radar"
        >
          <StatusRows emptyText="Risk Radar wird geladen." rows={riskItems} />
        </TechnicalSignalCard>
        <TechnicalSignalCard
          className="ai-knowledge-panel"
          contentClassName="ai-knowledge-health"
          description="Index, Quellen und Wissenslücken."
          title="Quellen & Wissensstatus"
        >
          <StatusRows emptyText="Wissensstatus wird geladen." rows={knowledgeItems} />
        </TechnicalSignalCard>
      </section>

      <section className="ops-dashboard-grid" aria-label="Weitere Statusdetails">
        <article className="ops-panel app-card">
          <header className="ops-panel-header">
            <h2>Warnsignale</h2>
            <a hidden={!canViewDashboard("errors")} href="/errors">
              Störungen
            </a>
          </header>
          <div className="activity-feed is-warning-feed">
            {warnings.length ? warnings.map((item) => <WarningItem item={item} key={`${item.label}-${item.value}`} />) : (
              <EmptyState>Keine kritischen Warnungen im aktuellen Datenfenster.</EmptyState>
            )}
          </div>
        </article>
        <article className="ops-panel app-card">
          <header className="ops-panel-header">
            <h2>Dokument-/Indexstatus</h2>
            <a hidden={!canViewDashboard("documents")} href="/documents">
              Dokumente
            </a>
          </header>
          <div className="ai-knowledge-health">
            {indexRows.map((row) => (
              <StatusRow key={row.label} row={row} />
            ))}
          </div>
        </article>
      </section>
    </details>
  );
}
