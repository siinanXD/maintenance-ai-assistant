export type Machine = {
  readonly id: number;
  readonly name: string;
  readonly produced_item?: string;
};

export type InventoryMaterial = {
  readonly id: number;
  readonly name: string;
  readonly unit_cost: number;
  readonly quantity: number;
  readonly min_quantity?: number;
  readonly manufacturer?: string;
  readonly machine_id?: number | null;
  readonly machine?: Machine | null;
  readonly total_value?: number;
};

type ForecastTask = {
  readonly title?: string;
};

type ForecastMaterial = {
  readonly name?: string;
};

type ForecastMachine = {
  readonly name?: string;
};

export type ForecastItem = {
  readonly material?: ForecastMaterial;
  readonly machine?: ForecastMachine;
  readonly quantity?: number;
  readonly risk_level?: string;
  readonly task?: ForecastTask;
  readonly recommended_action?: string;
  readonly match_reason?: string;
};

export type UnmatchedForecastTask = {
  readonly task: ForecastTask;
  readonly risk_level: string;
  readonly recommended_action?: string;
  readonly reason?: string;
};

export type InventoryForecast = {
  readonly items?: ForecastItem[];
  readonly unmatched_tasks?: UnmatchedForecastTask[];
  readonly summary?: {
    readonly critical?: number;
    readonly high?: number;
    readonly medium?: number;
  };
};
