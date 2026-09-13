import { apiRequest } from "../api/client";
import { listData, unwrapData } from "../api/payload";
import type { draftFromIncident } from "./taskUtils";
import type {
  Department,
  Task,
  TaskDraft,
  TaskPriorityItem
} from "./taskTypes";

type TaskAction = "start" | "complete";

/**
 * Load tasks visible to the current user.
 */
export async function loadTasks(): Promise<Task[]> {
  const response = await apiRequest<unknown>("/api/v1/tasks?limit=100");
  return listData<Task>(response);
}

/**
 * Load departments for the task form.
 */
export async function loadDepartments(): Promise<Department[]> {
  const response = await apiRequest<unknown>("/api/v1/departments");
  return listData<Department>(response);
}

/**
 * Create or update one task through the existing task API.
 */
export async function saveTask(draft: TaskDraft, editingTaskId: number | null): Promise<Task> {
  const path = editingTaskId ? `/api/v1/tasks/${editingTaskId}` : "/api/v1/tasks";
  const method = editingTaskId ? "PUT" : "POST";
  const body = Object.fromEntries(
    Object.entries(draft).filter(([, value]) => String(value).trim() !== "")
  );

  return apiRequest<Task>(path, { method, body });
}

/**
 * Start or complete an existing task.
 */
export async function runTaskAction(
  taskId: number,
  action: TaskAction,
  options: { readonly closeIncident?: boolean } = {}
): Promise<Task> {
  return unwrapData<Task>(
    await apiRequest<unknown>(`/api/v1/tasks/${taskId}/${action}`, {
      method: "POST",
      body: options.closeIncident ? { close_error_entry: true } : undefined
    })
  );
}

/**
 * Load one incident to prefill a work order.
 */
export async function loadIncident(errorId: number): Promise<IncidentForWorkOrder> {
  return apiRequest<IncidentForWorkOrder>(`/api/v1/errors/${errorId}`);
}

type IncidentForWorkOrder = Parameters<typeof draftFromIncident>[0];

/**
 * Delete an existing task through the existing task API.
 */
export async function deleteTask(taskId: number): Promise<void> {
  await apiRequest<null>(`/api/v1/tasks/${taskId}`, { method: "DELETE" });
}

/**
 * Request a non-persisted AI task suggestion.
 */
export async function suggestTask(text: string): Promise<TaskSuggestionPayload> {
  return unwrapData<TaskSuggestionPayload>(
    await apiRequest<unknown>("/api/v1/tasks/suggest", {
      method: "POST",
      body: { text }
    })
  );
}

/**
 * Request manual task prioritization for visible open tasks.
 */
export async function prioritizeTasks(): Promise<TaskPriorityItem[]> {
  return unwrapData<TaskPriorityItem[]>(
    await apiRequest<unknown>("/api/v1/tasks/prioritize", {
      method: "POST",
      body: { status: "open", limit: 10 }
    })
  );
}

type TaskSuggestionPayload = {
  readonly title?: string;
  readonly department?: string;
  readonly priority?: string;
  readonly status?: string;
  readonly description?: string;
  readonly possible_cause?: string;
  readonly recommended_action?: string;
};
