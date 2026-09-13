import { type ReactNode } from "react";

import { type DashboardPayload, type DashboardShiftCalendar } from "./dashboardApi";
import { type DashboardViewState } from "./dashboardModel";
import { absentEmployees, peopleText, relevantVacations } from "./dashboardPeopleModel";
import { briefingItems, briefingSummary } from "./dashboardSideModel";
import { shiftCalendarMessage } from "./dashboardShiftModel";
import {
  type DashboardAssetSignal,
  type DashboardFocusItem,
  dashboardAssetSignals,
  dashboardFocusItems,
  dashboardMachineHealthCounts
} from "./dashboardSituationModel";

type DashboardCockpitPanelsProps = {
  readonly dashboardState: DashboardViewState;
  readonly isShiftCalendarLoading: boolean;
  readonly onOpenTask: (taskId: number) => void;
  readonly shiftCalendar: DashboardShiftCalendar | null;
};

type PeopleDecision = {
  readonly actionLabel: string;
  readonly href: string;
  readonly meta: string;
  readonly title: string;
  readonly tone: "good" | "warning";
};

/**
 * Render common cockpit action content.
 */
function FocusActionContent({ action }: { readonly action: DashboardFocusItem }): ReactNode {
  return (
    <>
      <span className="cockpit-focus-marker">{action.marker}</span>
      <span className="cockpit-focus-copy">
        <small>{action.detail}</small>
        <strong>{action.title}</strong>
        <em>{action.meta || "Direkt prüfen"}</em>
      </span>
      <span className="cockpit-focus-action">{action.actionLabel}</span>
    </>
  );
}

/**
 * Render the primary action card for the immediate cockpit panel.
 */
function PrimaryActionCard({
  action,
  onOpenTask
}: {
  readonly action: DashboardFocusItem;
  readonly onOpenTask: (taskId: number) => void;
}): ReactNode {
  const className = `cockpit-focus-card is-${action.tone}`;

  if (action.taskId) {
    return (
      <button className={className} type="button" onClick={() => onOpenTask(action.taskId ?? 0)}>
        <FocusActionContent action={action} />
      </button>
    );
  }

  return (
    <a className={className} href={action.href || "#"}>
      <FocusActionContent action={action} />
    </a>
  );
}

/**
 * Render a secondary action row for the immediate cockpit panel.
 */
function SecondaryActionRow({
  action,
  onOpenTask
}: {
  readonly action: DashboardFocusItem;
  readonly onOpenTask: (taskId: number) => void;
}): ReactNode {
  const content = (
    <>
      <span>
        <strong>{action.title}</strong>
        <small>{action.meta || action.detail}</small>
      </span>
      <em>{action.marker}</em>
    </>
  );

  if (action.taskId) {
    return (
      <button className={`cockpit-mini-row is-${action.tone}`} type="button" onClick={() => onOpenTask(action.taskId ?? 0)}>
        {content}
      </button>
    );
  }

  return (
    <a className={`cockpit-mini-row is-${action.tone}`} href={action.href || "#"}>
      {content}
    </a>
  );
}

/**
 * Render the first cockpit panel as a priority queue instead of a long list.
 */
function ImmediateActionsPanel({ dashboardState, onOpenTask }: DashboardCockpitPanelsProps): ReactNode {
  const actions = dashboardFocusItems(dashboardState.data).slice(0, 3);
  const primaryAction = actions[0];
  const secondaryActions = actions.slice(1);

  return (
    <article className="ops-panel app-card cockpit-panel cockpit-action-panel">
      <header className="ops-panel-header">
        <div>
          <p className="section-kicker">Heute zuerst</p>
          <h2>Sofort handeln</h2>
        </div>
        <a className="panel-link" data-dashboard-nav="tasks" href="/tasks">
          Alle Aufgaben
        </a>
      </header>
      <div className="cockpit-panel-body cockpit-priority-body" data-dashboard-critical-today="">
        {dashboardState.isLoading ? <div className="empty-state">Kritische Lage wird geladen.</div> : null}
        {!dashboardState.isLoading && !primaryAction ? (
          <div className="cockpit-steady-card">
            <strong>Keine akute Eskalation</strong>
            <span>Neue Aufgaben und Störungen werden hier als Fokusfall angezeigt.</span>
          </div>
        ) : null}
        {primaryAction ? <PrimaryActionCard action={primaryAction} onOpenTask={onOpenTask} /> : null}
        {secondaryActions.length ? (
          <div className="cockpit-next-list" aria-label="Nächste Eskalationen">
            <span className="cockpit-section-label">Danach klären</span>
            {secondaryActions.map((action) => (
              <SecondaryActionRow key={action.id} action={action} onOpenTask={onOpenTask} />
            ))}
          </div>
        ) : null}
      </div>
    </article>
  );
}

/**
 * Render one small count badge in the asset cockpit panel.
 */
function AssetCountBadge({ label, value }: { readonly label: string; readonly value: number }): ReactNode {
  return (
    <span>
      <strong>{value}</strong>
      {label}
    </span>
  );
}

/**
 * Render the primary asset signal as a readable focus card.
 */
function PrimaryAssetCard({ signal }: { readonly signal: DashboardAssetSignal }): ReactNode {
  return (
    <a className={`cockpit-focus-card asset-focus-card is-${signal.tone}`} href={signal.href}>
      <span className="cockpit-focus-marker">ANL</span>
      <span className="cockpit-focus-copy">
        <small>{signal.status}</small>
        <strong>{signal.title}</strong>
        <em>{signal.meta || "Anlagenlage prüfen"}</em>
      </span>
      <span className="cockpit-focus-action">Details</span>
    </a>
  );
}

/**
 * Render one compact machine or incident signal row.
 */
function AssetSignalRow({ signal }: { readonly signal: DashboardAssetSignal }): ReactNode {
  return (
    <a className={`cockpit-mini-row is-${signal.tone}`} href={signal.href}>
      <span>
        <strong>{signal.title}</strong>
        <small>{signal.meta}</small>
      </span>
      <em>{signal.status}</em>
    </a>
  );
}

/**
 * Render the asset and incident cockpit panel as a health summary plus focus case.
 */
function AssetsIncidentsPanel({ dashboardState }: DashboardCockpitPanelsProps): ReactNode {
  const signals = dashboardAssetSignals(dashboardState.data);
  const primarySignal = signals[0];
  const secondarySignals = signals.slice(1, 3);
  const counts = dashboardMachineHealthCounts(dashboardState.data.machines);

  return (
    <article className="ops-panel app-card cockpit-panel cockpit-assets-panel">
      <header className="ops-panel-header">
        <div>
          <p className="section-kicker">Anlagen</p>
          <h2>Anlagen &amp; St&ouml;rungen</h2>
        </div>
        <a className="panel-link" data-dashboard-nav="machines" href="/machines">
          Maschinen
        </a>
      </header>
      <div className="cockpit-panel-body">
        <div className="asset-health-strip" data-dashboard-machine-strip="">
          <AssetCountBadge label="kritisch" value={counts.critical} />
          <AssetCountBadge label="beobachten" value={counts.warning} />
          <AssetCountBadge label="stabil" value={counts.good} />
        </div>
        {!dashboardState.isLoading && !primarySignal ? (
          <div className="cockpit-steady-card">
            <strong>Anlagenlage stabil</strong>
            <span>Keine aktiven Störungen oder kritischen Maschinenmeldungen.</span>
          </div>
        ) : null}
        {primarySignal ? <PrimaryAssetCard signal={primarySignal} /> : null}
        {secondarySignals.length ? (
          <div className="cockpit-next-list" aria-label="Weitere Anlagensignale">
            <span className="cockpit-section-label">Weitere Signale</span>
            {secondarySignals.map((signal) => (
              <AssetSignalRow key={signal.id} signal={signal} />
            ))}
          </div>
        ) : null}
      </div>
    </article>
  );
}

/**
 * Build the most important people decision for the cockpit.
 */
function peopleDecision(vacations: readonly DashboardPayload[], absent: readonly DashboardPayload[], employeeCount: number): PeopleDecision {
  if (vacations.length) {
    return {
      actionLabel: "Urlaub prüfen",
      href: "/vacations",
      meta: "Genehmigen oder ablehnen",
      title: `${vacations.length} Urlaubsanträge offen`,
      tone: "warning"
    };
  }

  if (absent.length) {
    return {
      actionLabel: "Personal ansehen",
      href: "/employees",
      meta: absent.slice(0, 2).map((employee) => peopleText(employee, "name", "Abwesend")).join(", "),
      title: `${absent.length} abwesend markiert`,
      tone: "warning"
    };
  }

  return {
    actionLabel: "Schicht ansehen",
    href: "/employees",
    meta: `${employeeCount || "--"} Mitarbeitende sichtbar`,
    title: "Keine Personalwarnung",
    tone: "good"
  };
}

/**
 * Render the primary people decision card.
 */
function PeopleDecisionCard({ decision }: { readonly decision: PeopleDecision }): ReactNode {
  return (
    <a className={`cockpit-focus-card people-focus-card is-${decision.tone}`} href={decision.href}>
      <span className="cockpit-focus-marker">TEAM</span>
      <span className="cockpit-focus-copy">
        <small>Offene Entscheidung</small>
        <strong>{decision.title}</strong>
        <em>{decision.meta}</em>
      </span>
      <span className="cockpit-focus-action">{decision.actionLabel}</span>
    </a>
  );
}

/**
 * Render one briefing link in the people cockpit panel.
 */
function BriefingLink({ item }: { readonly item: { readonly href?: string; readonly icon: string; readonly meta: string; readonly title: string } }): ReactNode {
  return (
    <a className="cockpit-mini-row is-muted" href={item.href || "#daily-briefing"}>
      <span>
        <strong>{item.title}</strong>
        <small>{item.meta}</small>
      </span>
      <em>{item.icon}</em>
    </a>
  );
}

/**
 * Render the shift, people, and briefing cockpit panel as one operational narrative.
 */
function PeopleBriefingPanel({
  dashboardState,
  isShiftCalendarLoading,
  shiftCalendar
}: DashboardCockpitPanelsProps): ReactNode {
  const vacations = relevantVacations(dashboardState.data.vacations);
  const absent = absentEmployees(dashboardState.data.employees);
  const decision = peopleDecision(vacations, absent, dashboardState.data.employees.length);
  const briefing = briefingItems(dashboardState.data).slice(0, 1);

  return (
    <article className="ops-panel app-card cockpit-panel cockpit-people-panel">
      <header className="ops-panel-header">
        <div>
          <p className="section-kicker">Schicht</p>
          <h2>Schicht &amp; Personal</h2>
        </div>
        <a className="panel-link" data-feature-key="handover" data-dashboard-nav="handover" href="/handover">
          Übergabe
        </a>
      </header>
      <div className="cockpit-panel-body">
        <div className="shift-status-line" data-dashboard-calendar-message="">
          {shiftCalendarMessage(shiftCalendar, isShiftCalendarLoading)}
        </div>
        <PeopleDecisionCard decision={decision} />
        <p className="briefing-summary cockpit-briefing-summary" data-daily-briefing-summary="">
          {briefingSummary(dashboardState.data, dashboardState.isInsightLoading)}
        </p>
        {briefing.length ? (
          <div className="cockpit-next-list cockpit-briefing-links" data-daily-briefing-list="">
            <span className="cockpit-section-label">Briefing</span>
            {briefing.map((item) => (
              <BriefingLink key={`${item.icon}-${item.title}-${item.meta}`} item={item} />
            ))}
          </div>
        ) : null}
      </div>
    </article>
  );
}

/**
 * Render the three-panel first viewport dashboard cockpit.
 */
export function DashboardCockpitPanels(props: DashboardCockpitPanelsProps): ReactNode {
  return (
    <section className="dashboard-cockpit-grid" aria-label="Operatives Tagescockpit">
      <ImmediateActionsPanel {...props} />
      <AssetsIncidentsPanel {...props} />
      <PeopleBriefingPanel {...props} />
    </section>
  );
}
