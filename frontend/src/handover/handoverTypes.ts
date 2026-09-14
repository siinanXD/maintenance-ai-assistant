export type Machine = {
  readonly id: number;
  readonly name: string;
};

export type HandoverRecord = {
  readonly id: number;
  readonly plan_id?: number | null;
  readonly department: string;
  readonly area?: string;
  readonly machine_id?: number | null;
  readonly machine?: Machine | null;
  readonly shift_date: string;
  readonly shift_type: string;
  readonly previous_shift?: string;
  readonly next_shift?: string;
  readonly status: string;
  readonly production_status?: string;
  readonly machine_status?: string;
  readonly safety_notes?: string;
  readonly material_notes?: string;
  readonly responsible_employee?: string;
  readonly problem_category?: string;
  readonly cause?: string;
  readonly action_taken?: string;
  readonly duration_minutes?: number;
  readonly follow_up_task?: string;
  readonly involved_employees?: string;
  readonly confirmed?: boolean;
  readonly handed_over_by?: string | null;
  readonly handed_over_at?: string | null;
  readonly content?: string;
  readonly open_tasks?: string;
  readonly machine_notes?: string;
  readonly next_notes?: string;
  readonly created_at?: string;
};

export type HandoverPayload = {
  readonly [key: string]: string | number | boolean | null | undefined;
};

export type HandoverFilters = {
  readonly department: string;
  readonly date: string;
  readonly machineId: string;
  readonly search: string;
  readonly shiftType: string;
  readonly status: string;
};

export type HandoverStats = {
  readonly completed: number;
  readonly followup: number;
  readonly open: number;
  readonly safety: number;
};

export type HandoverMessage = {
  readonly isError?: boolean;
  readonly text: string;
};
