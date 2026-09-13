export type Department = {
  readonly id?: number;
  readonly name: string;
};

export type ErrorStatus = "open" | "in_progress" | "closed";

export type ErrorSeverity = "critical" | "high" | "medium" | "low";

export type ErrorEntry = {
  readonly id: number;
  readonly machine?: string;
  readonly error_code?: string;
  readonly title?: string;
  readonly description?: string;
  readonly symptoms?: string;
  readonly possible_causes?: string;
  readonly solution?: string;
  readonly department?: Department | null;
  readonly status?: ErrorStatus | string;
  readonly severity?: ErrorSeverity | string;
  readonly cause_category?: string;
  readonly impact?: string;
  readonly downtime_minutes?: number | string | null;
  readonly production_loss_minutes?: number | string | null;
  readonly repeat_count?: number | string | null;
  readonly created_at?: string;
  readonly last_seen_at?: string;
  readonly closed_at?: string;
};

export type ErrorDraft = {
  department: string;
  machine: string;
  error_code: string;
  status: ErrorStatus;
  severity: ErrorSeverity;
  cause_category: string;
  title: string;
  symptoms: string;
  possible_causes: string;
  solution: string;
  impact: string;
  downtime_minutes: string;
  production_loss_minutes: string;
  repeat_count: string;
};

export type ErrorFilters = {
  readonly search: string;
  readonly status: string;
  readonly severity: string;
  readonly category: string;
  readonly quick: string;
};

export type MessageState = {
  readonly text: string;
  readonly error: boolean;
};

type SimilarErrorMatch = {
  readonly entry: ErrorEntry;
  readonly score: number;
  readonly reason?: string;
};

export type SimilarErrorResult = {
  readonly results?: readonly SimilarErrorMatch[];
};

type ErrorAssistantSource = {
  readonly title?: string;
  readonly source_type?: string;
  readonly url?: string;
  readonly score?: number;
};

export type ErrorAssistantResult = {
  readonly sources?: readonly ErrorAssistantSource[];
  readonly action_preview?: {
    readonly label?: string;
    readonly payload?: Record<string, unknown>;
  };
  readonly diagnostics?: {
    readonly rag_source_count?: number;
  };
};
