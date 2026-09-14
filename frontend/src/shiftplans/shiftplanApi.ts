import { apiRequest } from "../api/client";
import { listData, unwrapData } from "../api/payload";
import type {
  Machine,
  ShiftModel,
  ShiftPlan,
  ShiftplanChangeLog,
  ShiftplanConflictPayload,
  ShiftplanEditDraft,
  ShiftplanGenerationPayload,
} from "./shiftplanTypes";

const SHIFTPLANS_BASE = "/api/v1/shiftplans";

/**
 * Load all shift plans visible to the current user.
 */
export async function loadShiftPlans(): Promise<ShiftPlan[]> {
  return listData<ShiftPlan>(await apiRequest<unknown>(SHIFTPLANS_BASE));
}

/**
 * Load supported shift model templates.
 */
export async function loadShiftModels(): Promise<ShiftModel[]> {
  return listData<ShiftModel>(await apiRequest<unknown>(`${SHIFTPLANS_BASE}/models`));
}

/**
 * Load machines for shiftplan coverage selection.
 */
export async function loadShiftplanMachines(): Promise<Machine[]> {
  return listData<Machine>(await apiRequest<unknown>("/api/v1/machines?limit=200"));
}

/**
 * Generate a dry-run shift plan preview.
 */
export async function previewShiftPlan(payload: ShiftplanGenerationPayload): Promise<ShiftPlan> {
  return unwrapData<ShiftPlan>(await apiRequest<unknown>(`${SHIFTPLANS_BASE}/preview`, {
    method: "POST",
    body: payload,
  }));
}

/**
 * Generate and persist a shift plan.
 */
export async function generateShiftPlan(payload: ShiftplanGenerationPayload): Promise<ShiftPlan> {
  return unwrapData<ShiftPlan>(await apiRequest<unknown>(`${SHIFTPLANS_BASE}/generate`, {
    method: "POST",
    body: payload,
  }));
}

/**
 * Load validation conflicts for one persisted plan.
 */
export async function loadShiftplanConflicts(planId: number): Promise<ShiftplanConflictPayload> {
  return unwrapData<ShiftplanConflictPayload>(await apiRequest<unknown>(`${SHIFTPLANS_BASE}/${planId}/conflicts`));
}

/**
 * Toggle one shift plan between draft and published.
 */
export async function publishShiftPlan(planId: number): Promise<ShiftPlan> {
  return unwrapData<ShiftPlan>(await apiRequest<unknown>(`${SHIFTPLANS_BASE}/${planId}/publish`, { method: "PATCH" }));
}

/**
 * Delete one persisted shift plan.
 */
export async function deleteShiftPlan(planId: number): Promise<void> {
  await apiRequest<null>(`${SHIFTPLANS_BASE}/${planId}`, { method: "DELETE" });
}

/**
 * Update one shift plan entry.
 */
export async function updateShiftplanEntry(entryId: number, draft: ShiftplanEditDraft): Promise<ShiftPlan> {
  const payload: Record<string, string> = {
    shift: draft.shift,
    notes: draft.notes,
  };
  if (!["Frei", "Urlaub"].includes(draft.shift)) {
    payload.start_time = draft.startTime;
    payload.end_time = draft.endTime;
  }
  return unwrapData<ShiftPlan>(await apiRequest<unknown>(`${SHIFTPLANS_BASE}/entries/${entryId}`, {
    method: "PATCH",
    body: payload,
  }));
}

/**
 * Move one shift plan entry to an empty target slot.
 */
export async function moveEntryToSlot(entryId: number, targetDate: string, targetShift: string): Promise<ShiftPlan> {
  return unwrapData<ShiftPlan>(await apiRequest<unknown>(`${SHIFTPLANS_BASE}/entries/${entryId}/move`, {
    method: "PATCH",
    body: { target_date: targetDate, target_shift: targetShift },
  }));
}

/**
 * Move one shift plan entry onto another existing entry.
 */
export async function moveEntryToEntry(entryId: number, targetEntryId: number): Promise<ShiftPlan> {
  return unwrapData<ShiftPlan>(await apiRequest<unknown>(`${SHIFTPLANS_BASE}/entries/${entryId}/move`, {
    method: "PATCH",
    body: { target_entry_id: targetEntryId },
  }));
}

/**
 * Delete one shift plan entry.
 */
export async function deleteShiftplanEntry(entryId: number): Promise<void> {
  await apiRequest<null>(`${SHIFTPLANS_BASE}/entries/${entryId}`, { method: "DELETE" });
}

/**
 * Load changelog rows for one shift plan.
 */
export async function loadShiftplanChangelog(planId: number): Promise<ShiftplanChangeLog[]> {
  return listData<ShiftplanChangeLog>(await apiRequest<unknown>(`${SHIFTPLANS_BASE}/${planId}/changelog`));
}

/**
 * Return the download URL for one shift plan XLSX export.
 */
export function shiftplanExportUrl(planId: number): string {
  return `${SHIFTPLANS_BASE}/${planId}/export.xlsx`;
}
