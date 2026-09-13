import { type ReactNode } from "react";

import { type DashboardViewState } from "../dashboardModel";
import { type DashboardSituationCard, dashboardSituationCards } from "../dashboardSituationModel";

type DashboardSituationStripProps = {
  readonly dashboardState: DashboardViewState;
  readonly onOpenTask: (taskId: number) => void;
};

/**
 * Render the inside of one daily situation card.
 */
function SituationCardContent({ card }: { readonly card: DashboardSituationCard }): ReactNode {
  return (
    <>
      <span className="situation-value">{card.value}</span>
      <span className="situation-copy">
        <small>{card.label}</small>
        <strong>{card.title}</strong>
        <em>{card.detail}</em>
      </span>
      <span className="situation-action">{card.actionLabel}</span>
    </>
  );
}

/**
 * Render one clickable daily situation card.
 */
function SituationCard({
  card,
  onOpenTask
}: {
  readonly card: DashboardSituationCard;
  readonly onOpenTask: (taskId: number) => void;
}): ReactNode {
  const className = `situation-card is-${card.tone}`;

  if (card.taskId) {
    return (
      <button className={className} type="button" onClick={() => onOpenTask(card.taskId ?? 0)}>
        <SituationCardContent card={card} />
      </button>
    );
  }

  return (
    <a className={className} href={card.href || "#"}>
      <SituationCardContent card={card} />
    </a>
  );
}

/**
 * Render the summary row that makes the cockpit first viewport readable at a glance.
 */
export function DashboardSituationStrip({
  dashboardState,
  onOpenTask
}: DashboardSituationStripProps): ReactNode {
  const cards = dashboardSituationCards(dashboardState.data);

  return (
    <section className="dashboard-situation-strip" aria-label="Operative Tageslage">
      {cards.map((card) => (
        <SituationCard key={card.id} card={card} onOpenTask={onOpenTask} />
      ))}
    </section>
  );
}
