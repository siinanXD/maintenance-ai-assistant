import { useState, type ReactNode } from "react";

import { confirmAction } from "../../app/runtimeBridge";
import { AttachmentPanel } from "../../components/attachments/AttachmentPanel";
import { TaskMaterialsPanel } from "./TaskMaterialsPanel";
import { deleteTask, runTaskAction } from "../taskApi";
import type { MessageState, Task } from "../taskTypes";
import {
  formatDateTimeValue,
  priorityBadgeClass,
  priorityLabel,
  statusBadgeClass,
  statusLabel,
  taskDueLabel,
  taskDueState,
  taskErrorMessage,
  taskMachineHint,
  taskMetricLabel,
  taskOwnerLabel,
  taskTypeLabel
} from "../taskUtils";

type TaskCardProps = {
  readonly task: Task;
  readonly writable: boolean;
  readonly onEdit: (task: Task) => void;
  readonly onMessageChange: (message: MessageState) => void;
  readonly onMutated: () => Promise<void>;
  readonly onPrioritiesStale: () => void;
};

/**
 * Render one task card used by each kanban column.
 */
export function TaskCard({
  task,
  writable,
  onEdit,
  onMessageChange,
  onMutated,
  onPrioritiesStale
}: TaskCardProps): ReactNode {
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const dueState = taskDueState(task);

  /**
   * Run a status transition for this task.
   */
  async function handleTaskAction(action: "start" | "complete"): Promise<void> {
    setBusyAction(action);
    onMessageChange({
      text: action === "start" ? "Aufgabe wird gestartet..." : "Aufgabe wird abgeschlossen...",
      error: false
    });

    const incident = task.error_entry;
    const closeIncident = action === "complete" && incident && incident.status !== "closed"
      ? await confirmAction({ title: "Störung schließen", message: `Störung ${incident.error_code} „${incident.title}“ ebenfalls schließen?`, confirmText: "Schließen", cancelText: "Offen lassen" })
      : false;

    try {
      await runTaskAction(task.id, action, { closeIncident });
      await onMutated();
      onPrioritiesStale();
      onMessageChange({
        text: action === "start" ? "Aufgabe gestartet." : closeIncident ? "Aufgabe abgeschlossen, Störung geschlossen." : "Aufgabe abgeschlossen.",
        error: false
      });
    } catch (error) {
      onMessageChange({ text: taskErrorMessage(error), error: true });
    } finally {
      setBusyAction(null);
    }
  }

  /**
   * Delete this task after user confirmation.
   */
  async function handleDelete(): Promise<void> {
    if (!(await confirmAction({ title: "Aufgabe löschen", message: `Aufgabe „${task.title}“ wirklich löschen?`, confirmText: "Löschen" }))) {
      return;
    }

    setBusyAction("delete");
    try {
      await deleteTask(task.id);
      await onMutated();
      onPrioritiesStale();
      onMessageChange({ text: "Aufgabe gelöscht.", error: false });
    } catch (error) {
      onMessageChange({ text: taskErrorMessage(error), error: true });
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <article
      className={[
        "task-card",
        `is-${task.status || "open"}`,
        `is-priority-${task.priority || "normal"}`,
        dueState === "overdue" ? "is-overdue" : "",
        dueState === "today" ? "is-due-today" : ""
      ].filter(Boolean).join(" ")}
    >
      <div className="task-card-top">
        <div className="task-card-heading">
          <span className="task-type-badge">{taskTypeLabel(task)}</span>
          {task.error_entry ? (
            <a className="task-incident-link" href={`/errors?search=${encodeURIComponent(task.error_entry.error_code)}`}>
              Störung {task.error_entry.error_code}
            </a>
          ) : null}
          <h3 className="task-card-title">{task.title}</h3>
        </div>
        <div className="task-card-badges">
          <span className={priorityBadgeClass(task.priority)}>{priorityLabel(task.priority)}</span>
          <span className={statusBadgeClass(task.status)}>{statusLabel(task.status)}</span>
        </div>
      </div>

      <p className="task-card-description">{task.description || "Keine Beschreibung"}</p>

      <div className="task-card-meta">
        {[
          `Bereich: ${task.department?.name || "offen"}`,
          `Maschine: ${taskMachineHint(task)}`,
          taskDueLabel(task),
          `Verantwortlich: ${taskOwnerLabel(task)}`,
          taskMetricLabel(task)
        ].map((value) => (
          <span className={value.includes("Überfällig") ? "is-risk" : ""} key={value}>{value}</span>
        ))}
      </div>

      <div className="task-card-timeline">
        <span>
          <small>Erstellt</small>
          <strong>{formatDateTimeValue(task.created_at)}</strong>
        </span>
        {task.started_at ? (
          <span>
            <small>Gestartet</small>
            <strong>{formatDateTimeValue(task.started_at)}</strong>
          </span>
        ) : null}
        {task.completed_at ? (
          <span>
            <small>Abgeschlossen</small>
            <strong>{formatDateTimeValue(task.completed_at)}</strong>
          </span>
        ) : null}
      </div>

      <TaskMaterialsPanel open={task.status === "open" || task.status === "in_progress"} taskId={task.id} writable={writable} />
      <AttachmentPanel entityId={task.id} entityType="task" writable={writable} />

      <div className="task-card-actions">
        {writable && task.status === "open" ? (
          <button
            aria-label={`Aufgabe starten: ${task.title}`}
            className="btn btn-primary btn-sm"
            disabled={busyAction !== null}
            onClick={() => handleTaskAction("start")}
            type="button"
          >
            {busyAction === "start" ? "Läuft..." : "Starten"}
          </button>
        ) : null}
        {writable && task.status !== "done" && task.status !== "cancelled" ? (
          <button
            aria-label={`Aufgabe abschließen: ${task.title}`}
            className="btn btn-success btn-sm text-white"
            disabled={busyAction !== null}
            onClick={() => handleTaskAction("complete")}
            type="button"
          >
            {busyAction === "complete" ? "Läuft..." : "Abschließen"}
          </button>
        ) : null}
        {writable ? (
          <button className="btn btn-outline btn-sm" disabled={busyAction !== null} onClick={() => onEdit(task)} type="button">
            Bearbeiten
          </button>
        ) : null}
        {writable && task.status !== "in_progress" ? (
          <button className="btn btn-error btn-sm text-white" disabled={busyAction !== null} onClick={handleDelete} type="button">
            {busyAction === "delete" ? "Läuft..." : "Löschen"}
          </button>
        ) : null}
      </div>
    </article>
  );
}
