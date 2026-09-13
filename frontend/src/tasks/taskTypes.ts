export type TaskPriority = "urgent" | "soon" | "normal";

export type TaskStatus = "open" | "in_progress" | "done" | "cancelled";

export type TaskDueState = "overdue" | "today" | "planned" | "closed";

export type TaskBucket = "open" | "in_progress" | "done";

export type Department = {
  readonly id?: number;
  readonly name: string;
};

type TaskUser = {
  readonly id?: number;
  readonly name?: string;
  readonly username?: string;
  readonly email?: string;
};

export type Task = {
  readonly id: number;
  readonly title: string;
  readonly description?: string;
  readonly priority?: TaskPriority;
  readonly status?: TaskStatus;
  readonly due_date?: string | null;
  readonly created_at?: string | null;
  readonly started_at?: string | null;
  readonly completed_at?: string | null;
  readonly planned_minutes?: number | null;
  readonly actual_minutes?: number | null;
  readonly response_minutes?: number | null;
  readonly machine?: string | { readonly name?: string } | null;
  readonly machine_name?: string | null;
  readonly department?: Department | null;
  readonly creator?: TaskUser | null;
  readonly current_worker?: TaskUser | null;
  readonly completed_by_user?: TaskUser | null;
};

export type TaskDraft = {
  readonly title: string;
  readonly department: string;
  readonly priority: TaskPriority;
  readonly status: TaskStatus;
  readonly due_date: string;
  readonly description: string;
};

export type TaskFilters = {
  readonly search: string;
  readonly status: "" | TaskStatus;
  readonly priority: "" | TaskPriority;
  readonly department: string;
  readonly due: "" | Exclude<TaskDueState, "closed">;
};

export type TaskSuggestion = TaskDraft & {
  readonly possible_cause?: string;
  readonly recommended_action?: string;
};

export type TaskPriorityItem = {
  readonly task: Task;
  readonly score: number;
  readonly risk_level: "critical" | "high" | "medium" | "low" | string;
  readonly reason: string;
  readonly recommended_action: string;
};

export type MessageState = {
  readonly text: string;
  readonly error: boolean;
};
