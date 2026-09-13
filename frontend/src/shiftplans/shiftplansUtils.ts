import { safeErrorMessage } from "../utils/errors";
import type {
  ShiftKey,
  ShiftModel,
  ShiftPlan,
  ShiftplanCalendarSlot,
  ShiftplanDraft,
  ShiftplanEmployee,
  ShiftplanGenerationPayload,
  ShiftplanUnassignedSlot,
  ShiftplanVacationInput,
} from "./ShiftplansTypes";

export const SHIFT_WINDOWS: Readonly<Record<string, readonly [string, string]>> = {
  Frueh: ["06:00", "14:00"],
  Spaet: ["14:00", "22:00"],
  Nacht: ["22:00", "06:00"],
};

export const SHIFT_ORDER: readonly ShiftKey[] = ["Frueh", "Spaet", "Nacht", "Urlaub", "Frei"];

export const SHIFT_LABEL: Readonly<Record<string, string>> = {
  Frueh: "Frühschicht\n06:00-14:00",
  Spaet: "Spätschicht\n14:00-22:00",
  Nacht: "Nachtschicht\n22:00-06:00",
  Urlaub: "Urlaub",
  Frei: "Frei",
};

export const DAYS_DE: readonly string[] = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];

export const EMPTY_SHIFTPLAN_DRAFT: ShiftplanDraft = {
  department: "",
  days: "7",
  preferences: "",
  shiftModelKey: "",
  startDate: localIsoDate(new Date()),
  title: "",
  vacations: "",
};

/**
 * Return a local ISO date without UTC timezone shifts.
 */
export function localIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/**
 * Return a beginner-friendly label for a shift model.
 */
export function beginnerModelLabel(model: ShiftModel): string {
  const labels: Readonly<Record<string, string>> = {
    one_shift: "Tagschicht",
    two_shift: "2-Schicht Früh/Spät",
    three_shift: "3-Schicht Früh/Spät/Nacht",
    teilkonti: "Teilkonti",
    vollkonti_4: "Vollkonti 4-Schicht",
    vollkonti_5: "Vollkonti 5-Schicht",
  };
  return labels[model.key] || model.display_name || model.name || model.label || model.key;
}

/**
 * Format one shift model window for the preview.
 */
function formatShiftWindow(shift: { readonly label?: string; readonly name?: string; readonly key?: string; readonly start_time?: string; readonly end_time?: string }): string {
  const name = shift.label || shift.name || shift.key || "-";
  return `${name} ${shift.start_time || ""}-${shift.end_time || ""}`;
}

/**
 * Return a concise shift summary for a model.
 */
export function shiftSummary(model: ShiftModel): string {
  if (model.shifts_summary) return model.shifts_summary;
  return (model.shifts || []).map(formatShiftWindow).join(", ");
}

/**
 * Return a localized rotation label.
 */
export function rotationLabel(value?: string): string {
  if (value === "forward") return "Vorwärtsrotation Früh -> Spät -> Nacht";
  if (value === "fixed") return "Feste Tagschicht";
  return value || "-";
}

/**
 * Parse vacation text into API vacation rows.
 */
function parseVacationLines(text: string): ShiftplanVacationInput[] {
  return text.split("\n").flatMap((line) => {
    const parts = line.split(",").map((part) => part.trim());
    const employeeId = Number.parseInt(parts[0] || "", 10);
    if (Number.isInteger(employeeId) && parts[1]) {
      return [{ employee_id: employeeId, date: parts[1], notes: parts[2] || "" }];
    }
    return [];
  });
}

/**
 * Build and validate the generation payload for preview and persistence.
 */
export function buildGenerationPayload(
  draft: ShiftplanDraft,
  selectedModel: ShiftModel | null,
  selectedMachineIds: readonly number[]
): ShiftplanGenerationPayload {
  if (!draft.department) throw new Error("Bitte Abteilung wählen.");
  if (!draft.startDate) throw new Error("Bitte Startdatum angeben.");
  if (!selectedModel) throw new Error("Bitte ein Schichtmodell wählen.");
  if (!selectedMachineIds.length) throw new Error("Bitte mindestens eine Maschine auswählen.");
  return {
    department: draft.department,
    title: draft.title,
    start_date: draft.startDate,
    days: Number.parseInt(draft.days || "7", 10),
    shift_model_key: selectedModel.key,
    machine_ids: selectedMachineIds,
    rhythm: selectedModel.display_name || selectedModel.name || selectedModel.key,
    preferences: { text: draft.preferences },
    vacations: parseVacationLines(draft.vacations),
  };
}

/**
 * Return whether a shift plan entry is an unassigned coverage slot.
 */
export function isUnassignedSlot(entry: ShiftplanCalendarSlot): entry is ShiftplanUnassignedSlot & { readonly unassigned: true } {
  return "unassigned" in entry && entry.unassigned === true;
}

/**
 * Return a machine name from a shift plan slot.
 */
export function slotMachineName(entry: ShiftplanCalendarSlot): string {
  return entry.machine?.name || entry.machine_name || "";
}

/**
 * Return a display employee name for one calendar slot.
 */
export function slotEmployeeName(entry: ShiftplanCalendarSlot): string {
  if (isUnassignedSlot(entry)) return `Unbesetzt (${entry.missing || 1})`;
  return entry.employee?.name || "?";
}

/**
 * Return all calendar dates covered by a shift plan.
 */
export function planDates(plan: ShiftPlan): Date[] {
  const start = new Date(`${plan.start_date}T00:00:00`);
  return Array.from({ length: plan.days }, (_, index) => {
    const date = new Date(start);
    date.setDate(start.getDate() + index);
    return date;
  });
}

/**
 * Group entries by shift and date for fast rendering.
 */
export function calendarIndex(plan: ShiftPlan): Map<string, Map<string, ShiftplanCalendarSlot[]>> {
  const grouped = new Map<string, Map<string, ShiftplanCalendarSlot[]>>();
  const addSlot = (slot: ShiftplanCalendarSlot): void => {
    if (!grouped.has(slot.shift)) grouped.set(slot.shift, new Map());
    const byDate = grouped.get(slot.shift);
    if (!byDate) return;
    const items = byDate.get(slot.work_date) || [];
    byDate.set(slot.work_date, [...items, slot]);
  };
  plan.entries.forEach(addSlot);
  (plan.unassigned_slots || []).forEach((slot) => addSlot({ ...slot, unassigned: true }));
  return grouped;
}

/**
 * Return shifts that should be visible for a plan.
 */
export function activePlanShifts(plan: ShiftPlan): ShiftKey[] {
  const usedShifts = new Set<ShiftKey>();
  plan.entries.forEach((entry) => usedShifts.add(entry.shift));
  (plan.unassigned_slots || []).forEach((slot) => usedShifts.add(slot.shift));
  return SHIFT_ORDER.filter((shift) => usedShifts.has(shift));
}

/**
 * Calculate shift hours across midnight.
 */
function shiftHours(start: string, end: string): number {
  const [startHours, startMinutes] = start.split(":").map(Number);
  const [endHours, endMinutes] = end.split(":").map(Number);
  let duration = endHours * 60 + endMinutes - (startHours * 60 + startMinutes);
  if (duration <= 0) duration += 24 * 60;
  return duration / 60;
}

/**
 * Build employee fairness rows for the current plan.
 */
export function fairnessRows(plan: ShiftPlan): Array<{ readonly employee: ShiftplanEmployee; readonly frueh: number; readonly spaet: number; readonly nacht: number; readonly urlaub: number; readonly hours: number }> {
  const byEmployee = new Map<number, { employee: ShiftplanEmployee; frueh: number; spaet: number; nacht: number; urlaub: number; hours: number }>();
  plan.entries.forEach((entry) => {
    const employeeId = entry.employee?.id;
    if (!employeeId) return;
    const row = byEmployee.get(employeeId) || {
      employee: entry.employee || {},
      frueh: 0,
      spaet: 0,
      nacht: 0,
      urlaub: 0,
      hours: 0,
    };
    if (entry.shift === "Frueh") row.frueh += 1;
    if (entry.shift === "Spaet") row.spaet += 1;
    if (entry.shift === "Nacht") row.nacht += 1;
    if (entry.shift === "Urlaub") row.urlaub += 1;
    if (entry.start_time && entry.end_time) row.hours += shiftHours(entry.start_time, entry.end_time);
    byEmployee.set(employeeId, row);
  });
  return Array.from(byEmployee.values()).sort((left, right) => (
    (left.employee.name || "").localeCompare(right.employee.name || "", "de-DE")
  ));
}

/**
 * Format an unknown shiftplan error for UI display.
 */
export function shiftplansErrorMessage(error: unknown, fallback = "Schichtplanung konnte nicht verarbeitet werden."): string {
  return safeErrorMessage(error, fallback);
}
