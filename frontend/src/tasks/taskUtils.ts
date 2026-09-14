import { formatGermanDate, formatGermanDateTime, todayIsoDate } from "../utils/date";
import { safeErrorMessage } from "../utils/errors";
import { type Task, type TaskBucket, type TaskDraft, type TaskDueState, type TaskFilters, type TaskPriority, type TaskStatus, type TaskSuggestion } from "./taskTypes";

/**
 * Normalize German maintenance text for simple search and keyword detection.
 */
function keywordText(value: unknown): string {
  return String(value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/ue/g, "u")
    .replace(/ae/g, "a")
    .replace(/oe/g, "o");
}

/**
 * Return the German priority label.
 */
export function priorityLabel(priority: string | null | undefined): string {
  const labels: Record<string, string> = {
    urgent: "Kritisch",
    soon: "Bald",
    normal: "Normal"
  };
  return labels[priority || ""] || priority || "-";
}

/**
 * Return the German task status label.
 */
export function statusLabel(status: string | null | undefined): string {
  const labels: Record<string, string> = {
    open: "Offen",
    in_progress: "In Arbeit",
    done: "Erledigt",
    cancelled: "Abgebrochen"
  };
  return labels[status || ""] || status || "-";
}

/**
 * Return the task priority badge classes from the existing visual language.
 */
export function priorityBadgeClass(priority: string | null | undefined): string {
  if (priority === "urgent") return "badge priority-badge is-urgent";
  if (priority === "soon") return "badge priority-badge is-soon";
  return "badge priority-badge is-normal";
}

/**
 * Return the task status badge classes from the existing visual language.
 */
export function statusBadgeClass(status: string | null | undefined): string {
  if (status === "in_progress") return "badge status-badge is-progress";
  if (status === "done" || status === "cancelled") return "badge status-badge is-done";
  return "badge status-badge is-open";
}

/**
 * Return the priority score risk badge classes from the existing UI.
 */
export function riskBadgeClass(riskLevel: string): string {
  if (riskLevel === "critical") return "badge badge-error text-white";
  if (riskLevel === "high") return "badge badge-warning text-slate-900";
  if (riskLevel === "medium") return "badge badge-info text-white";
  return "badge badge-success text-white";
}

/**
 * Return today's local ISO date.
 */
function taskTodayIso(): string {
  return todayIsoDate();
}

/**
 * Return the visible due-state bucket for one task.
 */
export function taskDueState(task: Task): TaskDueState {
  if (task.status === "done" || task.status === "cancelled") return "closed";
  if (!task.due_date) return "planned";
  const today = taskTodayIso();
  if (task.due_date < today) return "overdue";
  if (task.due_date === today) return "today";
  return "planned";
}

/**
 * Format an ISO date as weekday, day and month.
 */
function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  return formatGermanDate(`${value}T00:00:00`, {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    dateOnly: true,
    fallback: "-"
  });
}

/**
 * Format a timestamp as day, month and time.
 */
export function formatDateTimeValue(value: string | null | undefined): string {
  if (!value) return "-";
  return formatGermanDateTime(value, {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    fallback: "-"
  });
}

/**
 * Return the human-readable due label for one task.
 */
export function taskDueLabel(task: Task): string {
  const state = taskDueState(task);
  if (state === "overdue") return `Überfällig seit ${formatDate(task.due_date)}`;
  if (state === "today") return "Heute fällig";
  if (state === "closed" && task.completed_at) return `Erledigt ${formatDateTimeValue(task.completed_at)}`;
  return task.due_date ? `Fällig ${formatDate(task.due_date)}` : "Keine Fälligkeit";
}

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
 * Return the lowercase text the task search matches against.
 */
function taskSearchText(task: Task): string {
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
 * Return a sort key: due state, then priority, status and due date.
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

const EMPTY_TASK_DRAFT: TaskDraft = {
  title: "",
  department: "",
  priority: "normal",
  status: "open",
  due_date: "",
  description: "",
  error_entry_id: ""
};

/**
 * Return a task draft prefilled with default values.
 */
export function createEmptyTaskDraft(): TaskDraft {
  return { ...EMPTY_TASK_DRAFT };
}

/**
 * Convert unknown API errors into a safe UI message.
 */
export function taskErrorMessage(error: unknown): string {
  return safeErrorMessage(error, "Die Anfrage konnte nicht verarbeitet werden.");
}

/**
 * Convert one task into a form draft for edit mode.
 */
export function draftFromTask(task: Task): TaskDraft {
  return {
    title: task.title || "",
    department: task.department?.name || "",
    priority: task.priority || "normal",
    status: task.status || "open",
    due_date: task.due_date || "",
    description: task.description || "",
    error_entry_id: ""
  };
}

/**
 * Normalize a raw suggestion payload into editable form data.
 */
export function normalizeSuggestion(value: Record<string, unknown>): TaskSuggestion {
  return {
    title: typeof value.title === "string" ? value.title : "",
    department: typeof value.department === "string" ? value.department : "",
    priority: normalizePriority(value.priority),
    status: normalizeStatus(value.status),
    due_date: "",
    description: typeof value.description === "string" ? value.description : "",
    possible_cause: typeof value.possible_cause === "string" ? value.possible_cause : "",
    recommended_action: typeof value.recommended_action === "string" ? value.recommended_action : ""
  };
}

/**
 * Convert a suggestion into the main task form draft.
 */
export function draftFromSuggestion(suggestion: TaskSuggestion): TaskDraft {
  return {
    title: suggestion.title,
    department: suggestion.department,
    priority: suggestion.priority,
    status: suggestion.status,
    due_date: "",
    description: [
      suggestion.description,
      suggestion.possible_cause ? `Mögliche Ursache: ${suggestion.possible_cause}` : "",
      suggestion.recommended_action ? `Nächste Aktion: ${suggestion.recommended_action}` : ""
    ].filter(Boolean).join("\n\n"),
    error_entry_id: ""
  };
}

const PRIORITY_BY_SEVERITY: Readonly<Record<string, TaskPriority>> = {
  critical: "urgent",
  high: "urgent",
  medium: "soon",
  low: "normal"
};

/**
 * Build a work order draft for an incident: code and title, what was observed,
 * the documented cause and fix, and a priority derived from the severity.
 */
export function draftFromIncident(entry: {
  readonly id: number;
  readonly error_code?: string;
  readonly title?: string;
  readonly machine?: string;
  readonly severity?: string;
  readonly symptoms?: string;
  readonly description?: string;
  readonly possible_causes?: string;
  readonly solution?: string;
  readonly department?: { readonly name: string } | null;
}): TaskDraft {
  return {
    title: [entry.error_code, entry.title].filter(Boolean).join(" – ").slice(0, 160),
    department: entry.department?.name || "",
    priority: PRIORITY_BY_SEVERITY[entry.severity || ""] || "normal",
    status: "open",
    due_date: "",
    description: [
      entry.machine ? `Maschine: ${entry.machine}` : "",
      entry.symptoms || entry.description ? `Befund: ${entry.symptoms || entry.description}` : "",
      entry.possible_causes ? `Mögliche Ursache: ${entry.possible_causes}` : "",
      entry.solution ? `Bekannte Lösung: ${entry.solution}` : ""
    ].filter(Boolean).join("\n\n"),
    error_entry_id: String(entry.id)
  };
}

/**
 * Consume the AI action preview session payload for tasks.
 */
export function consumeTaskActionPreview(): TaskDraft | null {
  try {
    const raw = window.sessionStorage.getItem("maintenance_ai_action_preview");
    if (!raw) return null;
    const preview = JSON.parse(raw) as { readonly target?: string; readonly payload?: Record<string, unknown> };
    if (!preview || preview.target !== "tasks" || !preview.payload?.title) return null;
    window.sessionStorage.removeItem("maintenance_ai_action_preview");
    return draftFromSuggestion(normalizeSuggestion(preview.payload));
  } catch {
    window.sessionStorage.removeItem("maintenance_ai_action_preview");
    return null;
  }
}

/**
 * Read the initial task search query from the current URL.
 */
export function initialTaskSearchQuery(): string {
  const query = new URLSearchParams(window.location.search);
  return query.get("search") || query.get("q") || "";
}

/**
 * Normalize an unknown priority value.
 */
function normalizePriority(value: unknown): TaskPriority {
  return value === "urgent" || value === "soon" || value === "normal" ? value : "normal";
}

/**
 * Normalize an unknown status value.
 */
function normalizeStatus(value: unknown): TaskStatus {
  return value === "open" || value === "in_progress" || value === "done" || value === "cancelled"
    ? value
    : "open";
}
