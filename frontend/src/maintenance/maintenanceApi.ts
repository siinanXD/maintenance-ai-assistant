import { apiRequest } from "../api/client";
import { listData, unwrapData } from "../api/payload";
import type { MachineOption, MaintenancePlan, MaintenanceRecord, PlanDraft, RecordDraft } from "./maintenanceTypes";

const PLANS_PATH = "/api/v1/machines/maintenance-plans";

/**
 * Load all visible maintenance and inspection plans.
 */
export async function loadPlans(): Promise<MaintenancePlan[]> {
  return listData<MaintenancePlan>(await apiRequest<unknown>(PLANS_PATH));
}

/**
 * Load machines for the plan form.
 */
export async function loadMachineOptions(): Promise<MachineOption[]> {
  return listData<MachineOption>(await apiRequest<unknown>("/api/v1/machines?limit=200"));
}

/**
 * Create a plan or update an existing one.
 */
export async function savePlan(draft: PlanDraft, planId: number | null): Promise<MaintenancePlan> {
  const body = {
    ...draft,
    interval_days: Number(draft.interval_days),
    machine_id: draft.machine_id ? Number(draft.machine_id) : null
  };
  return unwrapData<MaintenancePlan>(
    await apiRequest<unknown>(planId ? `${PLANS_PATH}/${planId}` : PLANS_PATH, {
      method: planId ? "PUT" : "POST",
      body
    })
  );
}

/**
 * Document one execution of a plan.
 */
export async function saveRecord(planId: number, draft: RecordDraft): Promise<{ readonly plan: MaintenancePlan; readonly record: MaintenanceRecord }> {
  return unwrapData(
    await apiRequest<unknown>(`${PLANS_PATH}/${planId}/records`, { method: "POST", body: draft })
  );
}

/**
 * Load the documented executions of a plan.
 */
export async function loadRecords(planId: number): Promise<MaintenanceRecord[]> {
  return listData<MaintenanceRecord>(await apiRequest<unknown>(`${PLANS_PATH}/${planId}/records`));
}
