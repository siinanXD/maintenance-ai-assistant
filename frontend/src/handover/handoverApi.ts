import { apiRequest } from "../api/client";
import { listData, unwrapData } from "../api/payload";
import type { HandoverFilters, HandoverPayload, HandoverRecord, Machine } from "./handoverTypes";

const HANDOVER_BASE = "/api/v1/handover";

/**
 * Load machines for handover assignment and filtering.
 */
export async function loadHandoverMachines(): Promise<Machine[]> {
  const payload = await apiRequest<unknown>("/api/v1/machines?limit=100");
  return listData<Machine>(payload);
}

/**
 * Load handovers using server-side filters except local search.
 */
export async function loadHandovers(filters: HandoverFilters): Promise<HandoverRecord[]> {
  const params = new URLSearchParams();
  if (filters.department) params.set("department", filters.department);
  if (filters.date) params.set("date", filters.date);
  if (filters.shiftType) params.set("shift_type", filters.shiftType);
  if (filters.status) params.set("status", filters.status);
  if (filters.machineId) params.set("machine_id", filters.machineId);

  const queryString = params.toString();
  const payload = await apiRequest<unknown>(
    queryString ? `${HANDOVER_BASE}?${queryString}` : HANDOVER_BASE
  );
  return listData<HandoverRecord>(payload);
}

/**
 * Create one shift handover record.
 */
export async function createHandover(payload: HandoverPayload): Promise<HandoverRecord> {
  const response = await apiRequest<unknown>(HANDOVER_BASE, {
    method: "POST",
    body: payload,
  });
  return unwrapData<HandoverRecord>(response);
}

/**
 * Update one open shift handover.
 */
export async function updateHandover(id: number, payload: HandoverPayload): Promise<HandoverRecord> {
  const response = await apiRequest<unknown>(`${HANDOVER_BASE}/${id}`, {
    method: "PATCH",
    body: payload,
  });
  return unwrapData<HandoverRecord>(response);
}

/**
 * Mark one shift handover as completed.
 */
export async function completeHandover(id: number): Promise<HandoverRecord> {
  const response = await apiRequest<unknown>(`${HANDOVER_BASE}/${id}/complete`, {
    method: "POST",
  });
  return unwrapData<HandoverRecord>(response);
}
