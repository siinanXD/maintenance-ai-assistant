import type { ReactNode } from "react";

import type { TaskPriorityItem } from "../taskTypes";
import { riskBadgeClass } from "../taskUtils";

type TaskPriorityPanelProps = {
  readonly busy: boolean;
  readonly items: readonly TaskPriorityItem[];
  readonly onRefresh: () => Promise<void>;
};

/**
 * Return the visual score class for one risk level.
 */
function scoreClassName(riskLevel: string): string {
  if (riskLevel === "critical" || riskLevel === "high") return "priority-score-num is-high";
  if (riskLevel === "medium") return "priority-score-num is-medium";
  return "priority-score-num is-low";
}

/**
 * Render the risk ranking after the user requested it.
 */
export function TaskPriorityPanel({
  busy,
  items,
  onRefresh
}: TaskPriorityPanelProps): ReactNode {
  return (
    <article className="task-priority-panel app-card">
      <header className="panel-header">
        <div>
          <h2 className="panel-title">Prioritätslage</h2>
          <p className="panel-meta">Offene Aufgaben nach Risiko, Fälligkeit und Kontext sortiert.</p>
        </div>
        <button
          className="btn btn-outline btn-sm"
          disabled={busy}
          onClick={onRefresh}
          type="button"
        >
          {busy ? "Wird geladen..." : "Aktualisieren"}
        </button>
      </header>
      <div className="priority-score-list">
        {items.map((item) => (
            <div className="priority-score-card" key={`${item.task.id}-${item.score}`}>
              <div className={scoreClassName(item.risk_level)}>{item.score}</div>
              <div className="priority-score-body">
                <div className="priority-score-top">
                  <span className={riskBadgeClass(item.risk_level)}>{item.risk_level}</span>
                  <span className="priority-score-title">{item.task.title}</span>
                </div>
                <p className="priority-score-reason">{item.reason}</p>
                <p className="priority-score-action">{item.recommended_action}</p>
              </div>
            </div>
          ))}
      </div>
    </article>
  );
}
