import type { ReactNode } from "react";

import type { MessageState, Task, TaskBucket, TaskFilters } from "../taskTypes";
import { taskBucket, taskSortScore } from "../taskUtils";
import { TaskCard } from "./TaskCard";
import { TaskFiltersBar } from "./TaskFilters";

type TaskBoardProps = {
  readonly allTasks: readonly Task[];
  readonly departmentOptions: readonly string[];
  readonly filters: TaskFilters;
  readonly tasks: readonly Task[];
  readonly writable: boolean;
  readonly onEdit: (task: Task) => void;
  readonly onFiltersChange: (filters: TaskFilters) => void;
  readonly onMessageChange: (message: MessageState) => void;
  readonly onMutated: () => Promise<void>;
  readonly onPrioritiesStale: () => void;
};

const COLUMN_META: ReadonlyArray<{
  readonly bucket: TaskBucket;
  readonly className: string;
  readonly kicker: string;
  readonly title: string;
  readonly hint: string;
  readonly empty: string;
}> = [
  {
    bucket: "open",
    className: "is-open",
    kicker: "Planen",
    title: "Offen",
    hint: "Neue und noch nicht gestartete Arbeit",
    empty: "Keine offenen Aufgaben."
  },
  {
    bucket: "in_progress",
    className: "is-progress",
    kicker: "Ausführen",
    title: "In Bearbeitung",
    hint: "Gestartete Aufgaben mit Verantwortlichen",
    empty: "Nichts in Bearbeitung."
  },
  {
    bucket: "done",
    className: "is-done",
    kicker: "Abschließen",
    title: "Erledigt",
    hint: "Abgeschlossene und abgebrochene Aufgaben",
    empty: "Noch nichts erledigt."
  }
];

/**
 * Return task groups keyed by kanban bucket.
 */
function groupTasksByBucket(tasks: readonly Task[]): Record<TaskBucket, Task[]> {
  const buckets: Record<TaskBucket, Task[]> = {
    open: [],
    in_progress: [],
    done: []
  };

  tasks.forEach((task) => {
    buckets[taskBucket(task.status)].push(task);
  });

  return buckets;
}

/**
 * Render the task kanban board and filters.
 */
export function TaskBoard({
  allTasks,
  departmentOptions,
  filters,
  tasks,
  writable,
  onEdit,
  onFiltersChange,
  onMessageChange,
  onMutated,
  onPrioritiesStale
}: TaskBoardProps): ReactNode {
  const buckets = groupTasksByBucket(tasks);

  return (
    <article className="task-board-shell app-card" id="task-list">
      <header className="task-board-header">
        <div>
          <p className="section-kicker">Arbeitssteuerung</p>
          <h2>Kanban-Board</h2>
          <p className="panel-meta">Aufgaben starten, abschließen, bearbeiten und nach operativen Kriterien filtern.</p>
        </div>
        <div className="task-legend" aria-label="Aufgabenlegende">
          <span className="badge priority-badge is-urgent">Kritisch</span>
          <span className="badge priority-badge is-soon">Bald</span>
          <span className="badge priority-badge is-normal">Normal</span>
          <span className="badge status-badge is-open">Offen</span>
          <span className="badge status-badge is-progress">In Arbeit</span>
          <span className="badge status-badge is-done">Erledigt</span>
        </div>
      </header>

      <TaskFiltersBar
        departments={departmentOptions}
        filters={filters}
        onFiltersChange={onFiltersChange}
        total={allTasks.length}
        visible={tasks.length}
      />

      <div className="kanban-board task-maintenance-board bounded-list-scroll">
        {COLUMN_META.map((column) => {
          const columnTasks = [...buckets[column.bucket]].sort((first, second) => (
            taskSortScore(first).localeCompare(taskSortScore(second))
          ));

          return (
            <section className={`kanban-column ${column.className}`} aria-labelledby={`react-task-kanban-${column.bucket}`} key={column.bucket}>
              <header className="kanban-column-header">
                <div>
                  <span className="section-kicker">{column.kicker}</span>
                  <h3 id={`react-task-kanban-${column.bucket}`}>{column.title}</h3>
                  <small>{column.hint}</small>
                </div>
                <span className="kanban-count">{columnTasks.length}</span>
              </header>
              <div className="kanban-list">
                {columnTasks.length ? (
                  columnTasks.map((task) => (
                    <TaskCard
                      key={task.id}
                      onEdit={onEdit}
                      onMessageChange={onMessageChange}
                      onMutated={onMutated}
                      onPrioritiesStale={onPrioritiesStale}
                      task={task}
                      writable={writable}
                    />
                  ))
                ) : (
                  <div className="empty-state kanban-empty-state">{column.empty}</div>
                )}
              </div>
            </section>
          );
        })}
      </div>
    </article>
  );
}
