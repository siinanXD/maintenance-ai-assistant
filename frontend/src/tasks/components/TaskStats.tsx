import type { ReactNode } from "react";

import type { Task } from "../taskTypes";
import { taskDueState } from "../taskUtils";

type TaskStatsProps = {
  readonly tasks: readonly Task[];
};

/**
 * Render the task KPI strip.
 */
export function TaskStats({ tasks }: TaskStatsProps): ReactNode {
  const open = tasks.filter((task) => task.status === "open").length;
  const progress = tasks.filter((task) => task.status === "in_progress").length;
  const done = tasks.filter((task) => task.status === "done").length;
  const overdue = tasks.filter((task) => taskDueState(task) === "overdue").length;

  return (
    <section className="task-control-strip" aria-label="Aufgaben Kennzahlen">
      <article className="task-control-stat is-open">
        <span>Offen</span>
        <strong data-task-open-count>{open}</strong>
        <small>bereit zur Einplanung</small>
      </article>
      <article className="task-control-stat is-progress">
        <span>In Bearbeitung</span>
        <strong data-task-progress-count>{progress}</strong>
        <small>laufende Arbeit</small>
      </article>
      <article className="task-control-stat is-risk">
        <span>Überfällig</span>
        <strong data-task-overdue-count>{overdue}</strong>
        <small>sofort prüfen</small>
      </article>
      <article className="task-control-stat is-done">
        <span>Erledigt</span>
        <strong data-task-done-count>{done}</strong>
        <small>abgeschlossen</small>
      </article>
    </section>
  );
}
