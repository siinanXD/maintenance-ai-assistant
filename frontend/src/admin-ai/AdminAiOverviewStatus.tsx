import { type ReactNode } from "react";

import {
  adminActionItems,
  overviewBadge,
  overviewCriticalCards,
  type AdminAiOverviewLoadState
} from "./adminAiOverviewModel";
import { displayText } from "./AdminAiOverviewShared";

/**
 * Render a compact Admin-AI operations cockpit focused on quick fault detection.
 */
export function AdminAiOverviewStatus({ overviewState }: { readonly overviewState: AdminAiOverviewLoadState }): ReactNode {
  const statusBadge = overviewBadge(overviewState);
  const criticalCards = overviewCriticalCards(overviewState);
  const actionItems = adminActionItems(overviewState);
  const errorEvents = overviewState.events.slice(0, 8);

  return (
    <>
      <div className="ai-admin-area-header">
        <div>
          <span className="section-kicker">Betrieb</span>
          <h3>AI Schnellcheck</h3>
          <p className="panel-meta">
            Nur die kritischen Signale: Bereitschaft, RAG, Antwortqualität und Hintergrundjobs.
          </p>
        </div>
        <span className={`badge badge-ai ${statusBadge.tone}`} data-ai-section-status="status">
          {statusBadge.label}
        </span>
      </div>

      <div className="ai-status-overview" data-ai-health-panel data-ai-status-overview aria-label="AI Betriebsstatus">
        {criticalCards.map(({ detail, key, label, tone, value }) => (
          <article className={`ai-status-overview-card ${tone}`} data-ai-status-overview-item={key} key={key}>
            <span>{label}</span>
            <strong data-ai-status-overview-label>{value}</strong>
            <small data-ai-status-overview-detail>{detail}</small>
          </article>
        ))}
      </div>

      <section className="panel ai-clarity-panel admin-control-action-summary" data-ai-admin-control-center>
        <div className="panel-header">
          <div>
            <h3>Handlungsbedarf</h3>
            <p className="panel-meta">Nur offene Probleme aus Status, RAG, Jobs und Feedback.</p>
          </div>
          <span className={`status-pill ${actionItems[0]?.tone || "is-muted"}`}>
            {actionItems[0]?.key === "none" ? "Keine Aktion" : `${actionItems.length} offen`}
          </span>
        </div>
        <ul className="action-hint-list" aria-label="Offene Admin-AI-Maßnahmen">
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

      <details className="help-disclosure ui-secondary-panel">
        <summary>
          Letzte AI-Fehler
          {errorEvents.length ? ` (${errorEvents.length})` : ""}
        </summary>
        <div className="help-disclosure-body">
          <div className="panel-header">
            <p className="panel-meta">Die letzten acht Audit-Ereignisse mit Fehlerkategorie.</p>
            <a className="btn btn-ghost btn-sm" href="/admin/ai/technical">
              Technische Details
            </a>
          </div>
          <div className="table-wrap bounded-table-wrap">
            <table className="data-table">
              <caption>Letzte KI-Fehler für schnelle Ursachenanalyse</caption>
              <thead>
                <tr>
                  <th scope="col">Zeit</th>
                  <th scope="col">Workflow</th>
                  <th scope="col">Status</th>
                  <th scope="col">Fehler</th>
                </tr>
              </thead>
              <tbody data-ai-events>
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
                      <span className="empty-state">Keine AI-Fehler in der letzten Auswertung.</span>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </details>
    </>
  );
}

/**
 * Render the explanatory Admin-AI overview intro.
 */
export function AdminAiOverviewIntro(): ReactNode {
  return (
    <details className="help-disclosure context-help ai-workflow-help" aria-label="So arbeitet die KI">
      <summary>So arbeitet die KI</summary>
      <div className="help-disclosure-body">
        <p className="panel-meta">
          Frage verstehen, Daten suchen, Kontext bauen, Sicherheit prüfen, Antwort mit Quellen liefern.
          Details finden Sie unter Testfrage prüfen und Wissensbasis pflegen.
        </p>
      </div>
    </details>
  );
}
