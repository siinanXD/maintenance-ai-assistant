import { apiRequest } from "../api/client";
import { isObjectPayload, listData, unwrapData } from "../api/payload";
import { todayIsoDate } from "../utils/date";
import { safeErrorMessage } from "../utils/errors";

export type DashboardPayload = Record<string, unknown>;

export type DashboardRuntimeData = {
  readonly aiStatus: DashboardPayload | null;
  readonly employees: readonly DashboardPayload[];
  readonly errors: readonly DashboardPayload[];
  readonly handovers: readonly DashboardPayload[];
  readonly inventorySummary: DashboardPayload | null;
  readonly knowledgeGaps: readonly DashboardPayload[];
  readonly knowledgeStatus: DashboardPayload | null;
  readonly loadErrors: readonly string[];
  readonly machines: readonly DashboardPayload[];
  readonly maintenancePlans: readonly DashboardPayload[];
  readonly operationsSummary: DashboardPayload | null;
  readonly dailyBriefing: DashboardPayload | null;
  readonly retrievalTelemetry: DashboardPayload | null;
  readonly tasks: readonly DashboardPayload[];
  readonly vacations: readonly DashboardPayload[];
};

export type DashboardTaskMutation = {
  readonly department?: string;
  readonly description?: string;
  readonly due_date?: string;
  readonly priority?: string;
  readonly status?: string;
  readonly title?: string;
};

export type DashboardTaskReportPayload = {
  readonly action?: string;
  readonly cause?: string;
  readonly generate_report?: boolean;
  readonly machine?: string;
  readonly notes?: string;
  readonly result?: string;
};

export type DashboardShiftCalendar = {
  readonly employee?: DashboardPayload | null;
  readonly entries?: readonly DashboardPayload[];
  readonly message?: string;
};

const EMPTY_DASHBOARD_DATA: DashboardRuntimeData = {
  aiStatus: null,
  employees: [],
  errors: [],
  handovers: [],
  inventorySummary: null,
  knowledgeGaps: [],
  knowledgeStatus: null,
  loadErrors: [],
  machines: [],
  maintenancePlans: [],
  operationsSummary: null,
  dailyBriefing: null,
  retrievalTelemetry: null,
  tasks: [],
  vacations: []
};

/**
 * Return a plain-object payload from a raw API response.
 */
function objectData(payload: unknown): DashboardPayload | null {
  const data = unwrapData<unknown>(payload);
  return isObjectPayload(data) ? data : null;
}

/**
 * Load one dashboard list endpoint with the shared React API client.
 */
async function loadDashboardList(path: string, signal?: AbortSignal): Promise<readonly DashboardPayload[]> {
  return listData<DashboardPayload>(await apiRequest<unknown>(path, { signal }));
}

/**
 * Load one dashboard object endpoint with the shared React API client.
 */
async function loadDashboardObject(path: string, signal?: AbortSignal): Promise<DashboardPayload | null> {
  return objectData(await apiRequest<unknown>(path, { signal }));
}

/**
 * Resolve a fulfilled dashboard result or collect a visible load error.
 */
function settledValue<TValue>(
  result: PromiseSettledResult<TValue>,
  fallback: TValue,
  label: string,
  errors: string[]
): TValue {
  if (result.status === "fulfilled") {
    return result.value;
  }

  errors.push(`${label}: ${safeErrorMessage(result.reason, "Daten konnten nicht geladen werden.")}`);
  return fallback;
}

type DashboardCoreData = Pick<
  DashboardRuntimeData,
  "employees" | "errors" | "handovers" | "inventorySummary" | "machines" | "maintenancePlans" | "operationsSummary" | "tasks" | "vacations"
> & { readonly loadErrors: readonly string[] };

type DashboardInsightData = Pick<
  DashboardRuntimeData,
  "aiStatus" | "dailyBriefing" | "knowledgeGaps" | "knowledgeStatus" | "retrievalTelemetry"
> & { readonly loadErrors: readonly string[] };

/**
 * Load the operational data the cockpit needs to render its first useful view.
 *
 * These endpoints answer in milliseconds. The cockpit renders as soon as they
 * settle instead of waiting for the AI insight endpoints below.
 */
export async function loadDashboardCoreData(signal?: AbortSignal): Promise<DashboardCoreData> {
  const [
    tasksResult,
    errorsResult,
    machinesResult,
    employeesResult,
    vacationsResult,
    handoversResult,
    inventoryResult,
    operationsResult,
    plansResult
  ] = await Promise.allSettled([
    loadDashboardList("/api/v1/tasks?limit=100", signal),
    loadDashboardList("/api/v1/errors?limit=100&active=1", signal),
    loadDashboardList("/api/v1/machines?limit=100", signal),
    loadDashboardList("/api/v1/employees?limit=200", signal),
    loadDashboardList("/api/v1/vacations?limit=100", signal),
    loadDashboardList(`/api/v1/handover?date=${todayIsoDate()}`, signal),
    loadDashboardObject("/api/v1/inventory/summary?include_materials=0", signal),
    loadDashboardObject(`/api/v1/operations/summary?from=${todayIsoDate()}&to=${todayIsoDate()}`, signal),
    loadDashboardList("/api/v1/machines/maintenance-plans", signal)
  ]);
  const loadErrors: string[] = [];

  return {
    employees: settledValue(employeesResult, [], "Mitarbeiter", loadErrors),
    errors: settledValue(errorsResult, [], "Störungen", loadErrors),
    handovers: settledValue(handoversResult, [], "Übergaben", loadErrors),
    inventorySummary: settledValue(inventoryResult, null, "Lager", loadErrors),
    loadErrors,
    machines: settledValue(machinesResult, [], "Maschinen", loadErrors),
    maintenancePlans: settledValue(plansResult, [], "Prüfungen", loadErrors),
    operationsSummary: settledValue(operationsResult, null, "Operations", loadErrors),
    tasks: settledValue(tasksResult, [], "Aufgaben", loadErrors),
    vacations: settledValue(vacationsResult, [], "Urlaub", loadErrors)
  };
}

/**
 * Load the AI insight data that may take seconds: briefing, AI and knowledge status.
 *
 * The daily briefing runs retrieval and an AI prioritization; it is loaded after
 * the cockpit is already visible and fills its panels when it arrives.
 */
export async function loadDashboardInsightData(signal?: AbortSignal): Promise<DashboardInsightData> {
  const [aiStatusResult, retrievalResult, knowledgeStatusResult, knowledgeGapsResult, briefingResult] =
    await Promise.allSettled([
      loadDashboardObject("/api/v1/ai/status", signal),
      loadDashboardObject("/api/v1/admin/ai/retrieval-telemetry?days=7&limit=5", signal),
      loadDashboardObject("/api/v1/admin/ai/knowledge/status", signal),
      loadDashboardList("/api/v1/admin/ai/knowledge-gaps?status=open&limit=5", signal),
      loadDashboardObject("/api/v1/ai/daily-briefing", signal)
    ]);
  const loadErrors: string[] = [];

  return {
    aiStatus: settledValue(aiStatusResult, null, "AI-Status", loadErrors),
    dailyBriefing: settledValue(briefingResult, null, "Briefing", loadErrors),
    knowledgeGaps: settledValue(knowledgeGapsResult, [], "Wissenslücken", loadErrors),
    knowledgeStatus: settledValue(knowledgeStatusResult, null, "Wissensstatus", loadErrors),
    loadErrors,
    retrievalTelemetry: settledValue(retrievalResult, null, "Retrieval", loadErrors)
  };
}

/**
 * Load one task for the React dashboard detail modal.
 */
export async function loadDashboardTask(taskId: number, signal?: AbortSignal): Promise<DashboardPayload> {
  return objectData(await apiRequest<unknown>(`/api/v1/tasks/${taskId}`, { signal })) ?? {};
}

/**
 * Start a task from the React dashboard.
 */
export async function startDashboardTask(taskId: number): Promise<DashboardPayload> {
  return objectData(await apiRequest<unknown>(`/api/v1/tasks/${taskId}/start`, { method: "POST" })) ?? {};
}

/**
 * Complete a task from the React dashboard.
 */
export async function completeDashboardTask(
  taskId: number,
  payload: DashboardTaskReportPayload
): Promise<DashboardPayload> {
  return objectData(
    await apiRequest<unknown>(`/api/v1/tasks/${taskId}/complete`, {
      body: payload,
      method: "POST"
    })
  ) ?? {};
}

/**
 * Update a task from the React dashboard detail form.
 */
export async function updateDashboardTask(
  taskId: number,
  payload: DashboardTaskMutation
): Promise<DashboardPayload> {
  return objectData(
    await apiRequest<unknown>(`/api/v1/tasks/${taskId}`, {
      body: payload,
      method: "PUT"
    })
  ) ?? {};
}

export { EMPTY_DASHBOARD_DATA };
