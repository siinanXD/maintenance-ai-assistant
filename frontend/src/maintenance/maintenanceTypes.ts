export type PlanKind = "maintenance" | "inspection";

export type DueState = "overdue" | "due_soon" | "ok" | "inactive";

export type RecordResult = "passed" | "defects" | "failed";

export type MaintenanceRecord = {
  readonly id: number;
  readonly performed_on: string;
  readonly performed_by: string;
  readonly result: RecordResult;
  readonly notes: string;
  readonly follow_up_task_id: number | null;
};

export type MaintenancePlan = {
  readonly id: number;
  readonly title: string;
  readonly kind: PlanKind;
  readonly legal_basis: string;
  readonly description: string;
  readonly interval_days: number;
  readonly next_due_date: string;
  readonly priority: "urgent" | "soon" | "normal";
  readonly is_active: boolean;
  readonly due_state: DueState;
  readonly machine_id: number | null;
  readonly machine: { readonly id: number; readonly name: string } | null;
  readonly department: { readonly name: string } | null;
  readonly last_record: MaintenanceRecord | null;
};

export type PlanDraft = {
  readonly title: string;
  readonly kind: PlanKind;
  readonly legal_basis: string;
  readonly description: string;
  readonly interval_days: string;
  readonly next_due_date: string;
  readonly machine_id: string;
  readonly priority: "urgent" | "soon" | "normal";
};

export type RecordDraft = {
  readonly performed_on: string;
  readonly performed_by: string;
  readonly result: RecordResult;
  readonly notes: string;
  readonly create_follow_up: boolean;
};

export type MachineOption = {
  readonly id: number;
  readonly name: string;
};
