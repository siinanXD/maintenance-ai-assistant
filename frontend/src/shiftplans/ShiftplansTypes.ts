export type ShiftKey = "Frueh" | "Spaet" | "Nacht" | "Urlaub" | "Frei" | string;

export type ShiftplansMessage = {
  readonly text: string;
  readonly isError?: boolean;
};

export type ShiftModel = {
  readonly key: string;
  readonly display_name?: string;
  readonly name?: string;
  readonly label?: string;
  readonly description?: string;
  readonly shifts_summary?: string;
  readonly shifts?: readonly ShiftModelWindow[];
  readonly team_count?: number;
  readonly weekend_operation?: boolean;
  readonly weekend_label?: string;
  readonly rotation_direction?: string;
  readonly rotation_label?: string;
  readonly recommended_rest_hours?: number;
};

type ShiftModelWindow = {
  readonly key?: string;
  readonly label?: string;
  readonly name?: string;
  readonly start_time?: string;
  readonly end_time?: string;
};

export type Machine = {
  readonly id: number;
  readonly name: string;
  readonly required_employees?: number;
};

export type ShiftplanDraft = {
  readonly department: string;
  readonly days: string;
  readonly preferences: string;
  readonly shiftModelKey: string;
  readonly startDate: string;
  readonly title: string;
  readonly vacations: string;
};

export type ShiftplanGenerationPayload = {
  readonly department: string;
  readonly title: string;
  readonly start_date: string;
  readonly days: number;
  readonly shift_model_key: string;
  readonly machine_ids: readonly number[];
  readonly rhythm: string;
  readonly preferences: {
    readonly text: string;
  };
  readonly vacations: readonly ShiftplanVacationInput[];
};

export type ShiftplanVacationInput = {
  readonly employee_id: number;
  readonly date: string;
  readonly notes: string;
};

export type ShiftplanEmployee = {
  readonly id?: number;
  readonly name?: string;
};

export type ShiftplanEntry = {
  readonly id: number;
  readonly employee?: ShiftplanEmployee | null;
  readonly end_time?: string | null;
  readonly machine?: Machine | null;
  readonly machine_id?: number | null;
  readonly machine_name?: string | null;
  readonly notes?: string | null;
  readonly shift: ShiftKey;
  readonly start_time?: string | null;
  readonly work_date: string;
};

export type ShiftplanUnassignedSlot = {
  readonly machine?: Machine | null;
  readonly machine_name?: string | null;
  readonly missing?: number;
  readonly shift: ShiftKey;
  readonly work_date: string;
};

export type ShiftplanCalendarSlot = ShiftplanEntry | (ShiftplanUnassignedSlot & { readonly unassigned: true });

export type ShiftPlan = {
  readonly id?: number;
  readonly title?: string;
  readonly department?: string;
  readonly start_date: string;
  readonly days: number;
  readonly status?: string;
  readonly is_preview?: boolean;
  readonly entries: readonly ShiftplanEntry[];
  readonly unassigned_slots?: readonly ShiftplanUnassignedSlot[];
  readonly warnings?: readonly ShiftplanWarning[];
};

export type ShiftplanWarning = {
  readonly severity?: string;
  readonly message?: string;
};

export type ShiftplanConflictPayload = {
  readonly conflicts?: readonly ShiftplanWarning[];
  readonly summary?: {
    readonly critical?: number;
  };
};

export type ShiftplanChangeLog = {
  readonly action?: string;
  readonly changed_at?: string;
  readonly field_name?: string | null;
  readonly new_value?: string | null;
  readonly old_value?: string | null;
  readonly user?: string | null;
};

export type ShiftplanEditDraft = {
  readonly endTime: string;
  readonly notes: string;
  readonly shift: string;
  readonly startTime: string;
};
