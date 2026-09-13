export type AdminPermission = {
  readonly can_view?: boolean;
  readonly can_write?: boolean;
  readonly employee_access_level?: string;
};

export type AdminUser = {
  readonly id: number;
  readonly username: string;
  readonly email: string;
  readonly role: string;
  readonly department?: { readonly name?: string } | null;
  readonly employee_id?: number | null;
  readonly is_active: boolean;
  readonly permissions?: Record<string, AdminPermission>;
};

export type AdminEmployee = {
  readonly id: number;
  readonly name: string;
  readonly personnel_number?: string;
};

type PermissionDashboard = {
  readonly key: string;
  readonly label: string;
  readonly supports_employee_access?: boolean;
};

type PermissionGroup = {
  readonly key: string;
  readonly label: string;
  readonly dashboards: readonly string[];
};

type EmployeeAccessLevel = {
  readonly key: string;
  readonly label: string;
};

export type PermissionSchema = {
  readonly dashboards: readonly PermissionDashboard[];
  readonly groups: readonly PermissionGroup[];
  readonly employee_access_levels: readonly EmployeeAccessLevel[];
  readonly role_defaults: Record<string, Record<string, AdminPermission>>;
};

export type AuditEntry = {
  readonly id?: number;
  readonly action?: string;
  readonly resource_type?: string;
  readonly resource_id?: number | string | null;
  readonly actor?: { readonly username?: string } | null;
  readonly created_at?: string;
};

export type BackupEntry = {
  readonly id: string;
  readonly filename: string;
  readonly size_bytes?: number;
  readonly created_at?: string;
  readonly download_url?: string;
};

export type AiSummary = {
  readonly events_total?: number;
  readonly fallback_count?: number;
  readonly feedback?: {
    readonly helpful_rate?: number | null;
    readonly not_helpful?: number;
  };
  readonly average_latency_ms?: number;
  readonly total_tokens?: number;
  readonly estimated_cost_usd?: number;
  readonly price_configuration?: {
    readonly configured?: boolean;
    readonly message?: string;
  };
  readonly user_metrics?: readonly AiUserMetric[];
  readonly workflow_counts?: Record<string, number>;
  readonly error_counts?: Record<string, number>;
  readonly latest_events?: readonly AiEvent[];
};

export type AiUserMetric = {
  readonly username?: string;
  readonly langfuse_user_id?: string;
  readonly events?: number;
  readonly total_tokens?: number;
  readonly estimated_cost_usd?: number;
  readonly fallback_rate?: number;
  readonly latest_used_at?: string;
};

export type AiEvent = {
  readonly workflow?: string;
  readonly status?: string;
  readonly model?: string;
  readonly source_count?: number;
  readonly latency_ms?: number;
  readonly fallback_used?: boolean;
  readonly created_at?: string;
};

export type MessageState = {
  readonly text: string;
  readonly error: boolean;
};
