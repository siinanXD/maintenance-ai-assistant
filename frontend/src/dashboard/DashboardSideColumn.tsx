import { type ReactNode } from "react";

import { type DashboardPayload } from "./dashboardApi";
import { type DashboardViewState } from "./dashboardModel";
import {
  activityItems,
  briefingItems,
  briefingSummary,
  inventoryMetrics,
  inventoryShortages,
  type BriefingItem
} from "./dashboardSideModel";

type DashboardSideColumnProps = {
  readonly dashboardState: DashboardViewState;
};

/**
 * Render one briefing or activity item.
 */
function FeedItem({ item }: { readonly item: BriefingItem }): ReactNode {
  const content = (
    <>
      <span>{item.icon}</span>
      <strong>{item.title}</strong>
      <small>{item.meta}</small>
    </>
  );

  return item.href ? (
    <a className={`briefing-item ${item.variant}`} href={item.href}>
      {content}
    </a>
  ) : (
    <div className={`briefing-item ${item.variant}`}>{content}</div>
  );
}

/**
 * Render the daily briefing card from React dashboard state.
 */
function DailyBriefingCard({ dashboardState }: DashboardSideColumnProps): ReactNode {
  const items = briefingItems(dashboardState.data);

  return (
    <article className="ops-panel app-card daily-briefing" id="daily-briefing" data-daily-briefing-card="">
      <header className="ops-panel-header">
        <div>
          <p className="section-kicker">Kurzlage</p>
          <h2>Tagesbriefing</h2>
          <p className="panel-meta">Automatisch verdichtete Lage.</p>
        </div>
        <span className="ai-label">AI</span>
      </header>
      <p className="briefing-summary" data-daily-briefing-summary="">
        {briefingSummary(dashboardState.data, dashboardState.isInsightLoading)}
      </p>
      <div className="briefing-list" data-daily-briefing-list="">
        {dashboardState.isInsightLoading ? (
          <div className="briefing-item is-warning">
            <span>AI</span>
            <strong>Kurzlage wird erstellt</strong>
            <small>Die übrigen Daten sind bereits aktuell.</small>
          </div>
        ) : null}
        {!dashboardState.isInsightLoading && items.length === 0 ? (
          <div className="stat-row">
            <span>Status</span>
            <strong>Keine Hinweise</strong>
          </div>
        ) : null}
        {items.map((item) => (
          <FeedItem key={`${item.icon}-${item.title}-${item.meta}`} item={item} />
        ))}
      </div>
    </article>
  );
}

/**
 * Render the activity feed card from React dashboard state.
 */
function ActivityFeedCard({ dashboardState }: DashboardSideColumnProps): ReactNode {
  const items = activityItems(dashboardState.data);

  return (
    <article className="ops-panel app-card">
      <header className="ops-panel-header">
        <div>
          <p className="section-kicker">Verlauf</p>
          <h2>Aktivit&auml;tsverlauf</h2>
          <p className="panel-meta">Neue Aufgaben, Fehler und Briefing-Signale.</p>
        </div>
      </header>
      <div className="activity-feed" data-dashboard-activity-feed="">
        {dashboardState.isLoading ? <div className="empty-state">Aktivitäten werden geladen.</div> : null}
        {!dashboardState.isLoading && items.length === 0 ? (
          <div className="empty-state">Noch keine Aktivitäten im aktuellen Datenfenster.</div>
        ) : null}
        {items.map((item) => (
          <FeedItem key={`${item.icon}-${item.title}-${item.meta}`} item={item} />
        ))}
      </div>
    </article>
  );
}

/**
 * Render one inventory metric.
 */
function InventoryMetric({ metric }: { readonly metric: { readonly detail: string; readonly label: string; readonly value: string } }): ReactNode {
  return (
    <div>
      <strong>{metric.label}</strong>
      <span>{metric.value}</span>
      <small>{metric.detail}</small>
    </div>
  );
}

/**
 * Render one shortage tag.
 */
function ShortageTag({ material }: { readonly material: DashboardPayload }): ReactNode {
  return (
    <span>
      {String(material.name || "Material")}
      <strong>{String(material.quantity || 0)} Stk.</strong>
    </span>
  );
}

/**
 * Render the inventory hints card from React dashboard state.
 */
function InventoryHintsCard({ dashboardState }: DashboardSideColumnProps): ReactNode {
  const metrics = inventoryMetrics(dashboardState.data);
  const shortages = inventoryShortages(dashboardState.data);

  return (
    <article className="ops-panel app-card">
      <header className="ops-panel-header">
        <div>
          <p className="section-kicker">Material</p>
          <h2>Lagerhinweise</h2>
          <p className="panel-meta">
            Kritische Teile und Engp&auml;sse f&uuml;r laufende Arbeit.
          </p>
        </div>
        <a data-dashboard-nav="inventory" hidden href="/inventory">
          Lager
        </a>
      </header>
      <div className="inventory-stats" data-dashboard-inventory-stats="">
        {metrics.map((metric) => (
          <InventoryMetric key={metric.label} metric={metric} />
        ))}
      </div>
      <div className="shortage-tags" aria-label="Top Engp&auml;sse" data-dashboard-inventory-shortages="">
        {dashboardState.isLoading ? <span>Lagerdaten werden geladen.</span> : null}
        {!dashboardState.isLoading && shortages.length === 0 ? <span>Keine Lagerdaten verfügbar.</span> : null}
        {shortages.map((material) => (
          <ShortageTag key={String(material.id ?? material.name)} material={material} />
        ))}
      </div>
    </article>
  );
}

/**
 * Render the dashboard side column as React-owned markup.
 */
export function DashboardSideColumn({ dashboardState }: DashboardSideColumnProps): ReactNode {
  return (
    <aside className="control-center-side-column" aria-label="Briefing und Aktivität">
      <DailyBriefingCard dashboardState={dashboardState} />
      <ActivityFeedCard dashboardState={dashboardState} />
      <InventoryHintsCard dashboardState={dashboardState} />
    </aside>
  );
}
