export type Machine = {
  readonly id: number;
  readonly name: string;
  readonly produced_item?: string;
  readonly required_employees?: number;
  readonly status?: string;
  readonly criticality?: string;
  readonly site?: { readonly name?: string } | null;
  readonly created_at?: string;
  readonly last_error?: string;
  readonly open_tasks?: number;
  readonly active_errors?: number;
};

export type MachineDraft = {
  readonly name: string;
  readonly produced_item: string;
  readonly required_employees: string;
};

export type MachineHistoryItem = {
  readonly type?: string;
  readonly date?: string;
  readonly title?: string;
  readonly status?: string;
  readonly summary?: string;
  readonly url?: string;
};

export type MachineHistory = {
  readonly machine: Machine;
  readonly summary?: { readonly text?: string };
  readonly source_counts?: Record<string, number>;
  readonly timeline?: readonly MachineHistoryItem[];
};

export type MachineRecommendation = {
  readonly machine?: Machine;
  readonly score?: number;
  readonly risk_level?: string;
  readonly reason?: string;
  readonly recommended_action?: string;
  readonly source_counts?: Record<string, number>;
};

export type MachineAssistantResponse = {
  readonly answer?: string;
  readonly diagnostics?: { readonly fallback_used?: boolean; readonly status?: string };
  readonly sources?: readonly MachineAssistantSource[];
};

export type MachineAssistantSource = {
  readonly title?: string;
  readonly source_type?: string;
  readonly type?: string;
  readonly url?: string;
  readonly score?: number;
};

export type MachineProfileRecord = Record<string, unknown>;

export type MachineProfile = {
  readonly machine?: Machine;
  readonly permissions?: Record<string, boolean>;
  readonly kpis?: Record<string, unknown>;
  readonly open_tasks?: readonly MachineProfileRecord[];
  readonly active_errors?: readonly MachineProfileRecord[];
  readonly error_history?: readonly MachineProfileRecord[];
  readonly documents?: {
    readonly reports?: readonly MachineProfileRecord[];
    readonly manuals?: readonly MachineProfileRecord[];
  };
  readonly maintenance_plans?: readonly MachineProfileRecord[];
  readonly shift_handovers?: readonly MachineProfileRecord[];
  readonly materials?: readonly MachineProfileRecord[];
  readonly timeline?: readonly MachineProfileRecord[];
};

export type MessageState = {
  readonly text: string;
  readonly error: boolean;
};
