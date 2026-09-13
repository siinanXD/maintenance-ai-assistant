import { type ReactNode } from "react";
import {
  adminActionItems,
  businessMetricRows,
  kpiValue,
  overviewBadge,
  overviewCriticalCards,
  type AdminAiOverviewLoadState
} from "../adminAiOverviewModel";
import { AdminAiOverviewActivity } from "./AdminAiOverviewActivity";
import { displayText } from "../adminAiFormat";
import { ADMIN_AI_VIEW_META, ADMIN_AI_WORKFLOW_AREAS } from "../adminAiViews";

type AdminAiOperateHubProps = {
  readonly overviewState: AdminAiOverviewLoadState;
};

/**
 * Render the simplified Admin-AI operations hub (monitoring entry point).
 */
export function AdminAiOperateHub({ overviewState }: AdminAiOperateHubProps): ReactNode {
  const statusBadge = overviewBadge(overviewState);
  const criticalCards = overviewCriticalCards(overviewState);
  const actionItems = adminActionItems(overviewState);
  const monitoringRows = businessMetricRows(overviewState).slice(0, 4);
  const errorEvents = overviewState.events.slice(0, 6);

  return (
    <section className="ai-admin-area ai-operate-hub" id="ai-models">
      <div className="ai-status-overview" aria-label="Betriebsstatus">
        {criticalCards.map(({ detail, key, label, tone, value }) => (
          <article className={`ai-status-overview-card ${tone}`} key={key}>
            <span>{label}</span>
            <strong>{value}</strong>
            <small>{detail}</small>
          </article>
        ))}
      </div>

      <nav className="ai-admin-workflow-nav" aria-label="KI-Administration Arbeitsbereiche">
        {ADMIN_AI_WORKFLOW_AREAS.map((area) => (
          <a className="ai-admin-workflow-card" href={area.href} key={area.view}>
            <span className="ai-admin-workflow-label">{area.label}</span>
            <strong>{area.title}</strong>
            <small>{area.lead}</small>
          </a>
        ))}
        <a className="ai-admin-workflow-card is-secondary" href={ADMIN_AI_VIEW_META.effectiveness.href}>
          <span className="ai-admin-workflow-label">{ADMIN_AI_VIEW_META.effectiveness.label}</span>
          <strong>{ADMIN_AI_VIEW_META.effectiveness.title}</strong>
          <small>{ADMIN_AI_VIEW_META.effectiveness.lead}</small>
        </a>
      </nav>

      <section className="panel ai-clarity-panel admin-control-action-summary">
        <div className="panel-header">
          <div>
            <h3>Handlungsbedarf</h3>
            <p className="panel-meta">Alerts aus Status, RAG, Jobs und Feedback.</p>
          </div>
          <span className={`status-pill ${statusBadge.tone}`}>{statusBadge.label}</span>
        </div>
        <ul className="action-hint-list" aria-label="Offene Betriebsmaßnahmen">
          {actionItems.map((item) => (
            <li className={`action-hint-item ${item.tone}`} key={item.key}>
              <div className="action-hint-copy">
                <strong>{item.label}</strong>
                <small>{item.detail}</small>
              </div>
              <span>{item.key === "none" ? "OK" : "Prüfen"}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel ai-operate-monitoring-panel">
        <div className="panel-header">
          <div>
            <h3>Monitoring-Kurzinfo</h3>
            <p className="panel-meta">Tokens, Kosten und Nutzung aus der Summary-API.</p>
          </div>
          <a className="btn btn-ghost btn-sm" href={ADMIN_AI_VIEW_META.effectiveness.href}>
            Details
          </a>
        </div>
        <div className="surface-stat-grid ai-operate-monitoring-grid">
          {monitoringRows.map((row) => (
            <article className="surface-stat-card is-neutral" key={row.label}>
              <span>{row.label}</span>
              <strong>{row.value}</strong>
            </article>
          ))}
          <article className="surface-stat-card is-ai">
            <span>Fallback-Rate</span>
            <strong>{kpiValue(overviewState.summary, "fallback_rate")}</strong>
          </article>
        </div>
      </section>

      <details className="help-disclosure ui-secondary-panel">
        <summary>
          Letzte Fehler-Events
          {errorEvents.length ? ` (${errorEvents.length})` : ""}
        </summary>
        <div className="help-disclosure-body">
          <div className="table-wrap bounded-table-wrap">
            <table className="data-table">
              <caption>Audit-Events für Logging und Ursachenanalyse</caption>
              <thead>
                <tr>
                  <th scope="col">Zeit</th>
                  <th scope="col">Workflow</th>
                  <th scope="col">Status</th>
                  <th scope="col">Fehler</th>
                </tr>
              </thead>
              <tbody>
                {errorEvents.length ? errorEvents.map((eventItem) => (
                  <tr key={displayText(eventItem.id || `${eventItem.created_at}-${eventItem.workflow}`)}>
                    <td>{displayText(eventItem.created_at)}</td>
                    <td>{displayText(eventItem.workflow)}</td>
                    <td>{displayText(eventItem.status)}</td>
                    <td>{displayText(eventItem.error_category)}</td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={4}>
                      <span className="empty-state">Keine Fehler-Events in der letzten Auswertung.</span>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <a className="btn btn-ghost btn-sm" href={ADMIN_AI_VIEW_META.technical.href}>
            Observability öffnen
          </a>
        </div>
      </details>

      <AdminAiOverviewActivity overviewState={overviewState} />
    </section>
  );
}
