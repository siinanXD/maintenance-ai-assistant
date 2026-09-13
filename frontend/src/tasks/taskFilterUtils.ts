import { keywordText, priorityLabel, statusLabel } from "./taskLabels";
import { taskDueState } from "./taskDateUtils";
import type { Task, TaskBucket, TaskFilters, TaskStatus } from "./taskTypes";

/**
 * Return the best visible machine hint for one task.
 */
export function taskMachineHint(task: Task): string {
  const explicit = task.machine_name || (typeof task.machine === "object" ? task.machine?.name : task.machine);
  if (typeof explicit === "string" && explicit.trim()) return explicit.trim();
  const text = [task.title, task.description].filter(Boolean).join(" ");
  const match = text.match(/\b(Maschine|Anlage|Presse|Linie|Roboter|CNC|Band)\s*[A-Za-z0-9\-_.]*/i);
  return match ? match[0] : "–";
}

/**
 * Return the operational type label inferred from task text.
 */
export function taskTypeLabel(task: Task): string {
  const text = keywordText([task.title, task.description].filter(Boolean).join(" "));
  if (text.includes("sicherheit") || text.includes("not-aus") || text.includes("schutz")) return "Sicherheit";
  if (text.includes("repar") || text.includes("defekt") || text.includes("storung")) return "Reparatur";
  if (text.includes("pruf") || text.includes("kontroll") || text.includes("check")) return "Prüfung";
  if (text.includes("reinig") || text.includes("sauber")) return "Reinigung";
  if (text.includes("produktion") || text.includes("auftrag") || text.includes("linie")) return "Produktion";
  if (text.includes("wart") || text.includes("service") || text.includes("inspektion")) return "Wartung";
  return "Aufgabe";
}

/**
 * Return the visible owner label for one task.
 */
export function taskOwnerLabel(task: Task): string {
  const worker = task.current_worker || task.completed_by_user || task.creator;
  if (!worker) return "nicht zugewiesen";
  return worker.name || worker.username || worker.email || `User #${worker.id}`;
}

/**
 * Return the visible time metric label for one task.
 */
export function taskMetricLabel(task: Task): string {
  if (task.actual_minutes) return `Ist ${task.actual_minutes} min`;
  if (task.planned_minutes) return `Plan ${task.planned_minutes} min`;
  if (task.response_minutes) return `Reaktion ${Math.round(task.response_minutes)} min`;
  return "Zeit offen";
}

/**
 * Return the searchable text used by filters and data-search-text hooks.
 */
export function taskSearchText(task: Task): string {
  return [
    task.title,
    task.description,
    task.priority,
    priorityLabel(task.priority),
    task.status,
    statusLabel(task.status),
    task.department?.name,
    taskMachineHint(task),
    taskTypeLabel(task),
    taskOwnerLabel(task),
    task.due_date
  ].filter(Boolean).join(" ").toLowerCase();
}

/**
 * Return a stable sort score equivalent to the legacy task workflow.
 */
export function taskSortScore(task: Task): string {
  const priorityRank: Record<string, number> = { urgent: 0, soon: 1, normal: 2 };
  const statusRank: Record<string, number> = { in_progress: 0, open: 1, done: 2, cancelled: 3 };
  const dueRank: Record<string, number> = { overdue: 0, today: 1, planned: 2, closed: 3 };
  return [
    dueRank[taskDueState(task)] ?? 4,
    priorityRank[task.priority || ""] ?? 3,
    statusRank[task.status || ""] ?? 4,
    task.due_date || "9999-12-31"
  ].join("|");
}

/**
 * Return true when a task matches the active filters.
 */
export function taskMatchesFilters(task: Task, filters: TaskFilters): boolean {
  const search = filters.search.trim().toLowerCase();
  if (search && !taskSearchText(task).includes(search)) return false;
  if (filters.status && task.status !== filters.status) return false;
  if (filters.priority && task.priority !== filters.priority) return false;
  if (filters.department && task.department?.name !== filters.department) return false;
  if (filters.due && taskDueState(task) !== filters.due) return false;
  return true;
}

/**
 * Return the kanban bucket for one task status.
 */
export function taskBucket(status: TaskStatus | undefined): TaskBucket {
  if (status === "done" || status === "cancelled") return "done";
  if (status === "in_progress") return "in_progress";
  return "open";
}
