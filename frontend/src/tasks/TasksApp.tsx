import {
  useEffect,
  useMemo,
  useState,
  type ReactNode
} from "react";

import { markIslandMounted } from "../app/islandMount";
import { canWriteDashboard } from "../auth/permissions";
import { ActionDrawer } from "../components/ui/ActionDrawer";
import { createActionDefinition } from "../components/ui/createActionSchema";
import { loadDepartments, loadIncident, loadTasks, prioritizeTasks } from "./taskApi";
import { TaskBoard } from "./components/TaskBoard";
import { TaskFormPanel } from "./components/TaskFormPanel";
import { TaskHeader } from "./components/TaskHeader";
import { TaskPriorityPanel } from "./components/TaskPriorityPanel";
import { TaskStats } from "./components/TaskStats";
import { TaskSuggestionPanel } from "./components/TaskSuggestionPanel";
import type {
  Department,
  MessageState,
  Task,
  TaskDraft,
  TaskFilters,
  TaskPriorityItem
} from "./taskTypes";
import {
  consumeTaskActionPreview,
  createEmptyTaskDraft,
  draftFromIncident,
  draftFromTask,
  initialTaskSearchQuery,
  taskErrorMessage,
  taskMatchesFilters,
  taskSortScore
} from "./taskUtils";

const TASKS_ISLAND = {
  mountedFlag: "maintenanceTasksReactMounted",
  mountEvent: "maintenance-tasks-react-mounted"
};

/**
 * Return the visible department filter options from loaded tasks.
 */
function departmentOptionsFromTasks(tasks: readonly Task[]): string[] {
  return Array.from(new Set(
    tasks.map((task) => task.department?.name).filter((name): name is string => Boolean(name))
  )).sort((first, second) => first.localeCompare(second, "de-DE"));
}

/**
 * Render the React task workflow island.
 */
export function TasksApp(): ReactNode {
  const writable = canWriteDashboard("tasks");
  const [activeDrawer, setActiveDrawer] = useState<"task" | "suggestion" | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [editingTaskId, setEditingTaskId] = useState<number | null>(null);
  const [filters, setFilters] = useState<TaskFilters>({
    search: initialTaskSearchQuery(),
    status: "",
    priority: "",
    department: "",
    due: ""
  });
  const [formDraft, setFormDraft] = useState<TaskDraft>(createEmptyTaskDraft());
  const [message, setMessage] = useState<MessageState>({ text: "", error: false });
  const [priorityBusy, setPriorityBusy] = useState(false);
  const [priorityItems, setPriorityItems] = useState<TaskPriorityItem[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);

  const departmentOptions = useMemo(() => departmentOptionsFromTasks(tasks), [tasks]);
  const visibleTasks = useMemo(() => (
    tasks
      .filter((task) => taskMatchesFilters(task, filters))
      .sort((first, second) => taskSortScore(first).localeCompare(taskSortScore(second)))
  ), [filters, tasks]);

  /**
   * Load departments and visible tasks in parallel.
   */
  async function refreshTaskData(): Promise<void> {
    const [loadedDepartments, loadedTasks] = await Promise.all([
      loadDepartments(),
      loadTasks()
    ]);
    setDepartments(loadedDepartments);
    setTasks(loadedTasks);
  }

  /**
   * Mark the manual priority result stale after task mutations.
   */
  function markPrioritiesStale(): void {
    setPriorityItems([]);
  }

  /**
   * Load manual task priorities on explicit user action.
   */
  async function refreshPriorities(): Promise<void> {
    setPriorityBusy(true);

    try {
      const priorities = await prioritizeTasks();
      setPriorityItems(priorities);
      setMessage({
        text: priorities.length ? "Prioritätslage aktualisiert." : "Keine offenen Aufgaben zu bewerten.",
        error: false
      });
    } catch {
      setPriorityItems([]);
      setMessage({ text: "Priorisierung konnte nicht geladen werden. Die Liste bleibt nach Fälligkeit sortiert.", error: true });
    } finally {
      setPriorityBusy(false);
    }
  }

  /**
   * Cancel the current task edit state.
   */
  function cancelEdit(): void {
    setEditingTaskId(null);
    setFormDraft(createEmptyTaskDraft());
    setMessage({ text: "Bearbeitung abgebrochen.", error: false });
    setActiveDrawer(null);
  }

  /**
   * Open the task form in edit mode.
   */
  function editTask(task: Task): void {
    setEditingTaskId(task.id);
    setFormDraft(draftFromTask(task));
    setActiveDrawer("task");
  }

  /**
   * Apply draft data from AI preview or suggestion to the form.
   */
  function applyDraft(draft: TaskDraft): void {
    setEditingTaskId(null);
    setFormDraft(draft);
    setActiveDrawer("task");
  }

  /**
   * Refresh data after create or update operations.
   */
  async function handleTaskSaved(): Promise<void> {
    setEditingTaskId(null);
    await refreshTaskData();
    markPrioritiesStale();
    setActiveDrawer(null);
  }

  useEffect(() => {
    markIslandMounted(TASKS_ISLAND);
  }, []);

  useEffect(() => {
    refreshTaskData().catch((error: unknown) => {
      setMessage({ text: taskErrorMessage(error), error: true });
    });

    const incidentId = Number(new URLSearchParams(window.location.search).get("from_error"));
    const previewDraft = consumeTaskActionPreview();
    if (incidentId > 0) {
      loadIncident(incidentId)
        .then((incident) => applyDraft(draftFromIncident(incident)))
        .catch((error: unknown) => setMessage({ text: taskErrorMessage(error), error: true }));
    } else if (previewDraft) {
      setFormDraft(previewDraft);
      setActiveDrawer("task");
    } else if (window.location.hash === "#task-create") {
      setActiveDrawer("task");
    }
  }, []);

  return (
    <>
      <TaskHeader
        onCreateFromMessage={() => setActiveDrawer("suggestion")}
        onCreateTask={() => {
          setEditingTaskId(null);
          setFormDraft(createEmptyTaskDraft());
          setActiveDrawer("task");
        }}
        onRefreshPriorities={refreshPriorities}
        priorityBusy={priorityBusy}
        writable={writable}
      />
      <TaskStats tasks={tasks} />
      {message.text && activeDrawer === null ? (
        <p className={`workflow-status${message.error ? " is-error" : ""}`} role="status">{message.text}</p>
      ) : null}
      {priorityItems.length ? (
        <section className="task-workflow-grid" aria-label="Aufgaben Workflows">
          <TaskPriorityPanel busy={priorityBusy} items={priorityItems} onRefresh={refreshPriorities} />
        </section>
      ) : null}
      <TaskBoard
        allTasks={tasks}
        departmentOptions={departmentOptions}
        filters={filters}
        onEdit={editTask}
        onFiltersChange={setFilters}
        onMessageChange={setMessage}
        onMutated={refreshTaskData}
        onPrioritiesStale={markPrioritiesStale}
        tasks={visibleTasks}
        writable={writable}
      />
      <ActionDrawer
        definition={createActionDefinition("taskCreate")}
        isOpen={activeDrawer === "task"}
        onClose={cancelEdit}
        title={editingTaskId ? "Aufgabe bearbeiten" : undefined}
      >
        <TaskFormPanel
          departments={departments}
          drawerMode
          draft={formDraft}
          editingTaskId={editingTaskId}
          hidden={!writable}
          message={message}
          onCancelEdit={cancelEdit}
          onDraftChange={setFormDraft}
          onMessageChange={setMessage}
          onSaved={handleTaskSaved}
        />
      </ActionDrawer>
      <ActionDrawer
        definition={createActionDefinition("taskSuggestion")}
        isOpen={activeDrawer === "suggestion"}
        onClose={() => setActiveDrawer(null)}
      >
        <TaskSuggestionPanel hidden={!writable} onApplySuggestion={applyDraft} />
      </ActionDrawer>
    </>
  );
}
