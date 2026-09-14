import { formatGermanDate, formatGermanDateTime } from "../utils/date";
import { safeErrorMessage } from "../utils/errors";
import {
  MACHINE_STATUS_OPTIONS,
  PRODUCTION_STATUS_OPTIONS,
  SHIFT_OPTIONS,
} from "./handoverOptions";
import type { HandoverFilters, HandoverRecord, HandoverStats } from "./handoverTypes";

export const EMPTY_HANDOVER_FILTERS: HandoverFilters = {
  department: "",
  date: "",
  machineId: "",
  search: "",
  shiftType: "",
  status: "",
};

const SHIFT_ORDER = ["Frueh", "Spaet", "Nacht"] as const;
const SHIFT_LABELS = Object.fromEntries(SHIFT_OPTIONS.map((option) => [option.value, option.label]));
const PRODUCTION_STATUS_LABELS = Object.fromEntries(
  PRODUCTION_STATUS_OPTIONS.map((option) => [option.value, option.label])
);
const MACHINE_STATUS_LABELS = Object.fromEntries(
  MACHINE_STATUS_OPTIONS.map((option) => [option.value, option.label])
);

/**
 * Return a safe display label for a shift key.
 */
export function shiftLabel(value: unknown): string {
  return SHIFT_LABELS[String(value || "")] || String(value || "-");
}

/**
 * Return a safe display label for production status.
 */
export function productionStatusLabel(value: unknown): string {
  return PRODUCTION_STATUS_LABELS[String(value || "")] || "Nicht bewertet";
}

/**
 * Return a safe display label for machine status.
 */
export function machineStatusLabel(value: unknown): string {
  return MACHINE_STATUS_LABELS[String(value || "")] || "Nicht bewertet";
}

/**
 * Return the adjacent shift in the standard three-shift cycle.
 */
export function adjacentShift(shiftType: string, offset: number): string {
  const index = SHIFT_ORDER.indexOf(shiftType as (typeof SHIFT_ORDER)[number]);
  if (index < 0) return "";
  return SHIFT_ORDER[(index + offset + SHIFT_ORDER.length) % SHIFT_ORDER.length];
}

/**
 * Return a formatted handover date.
 */
export function handoverDateLabel(value: unknown): string {
  return formatGermanDate(value, {
    dateOnly: true,
    day: "2-digit",
    fallback: "-",
    month: "2-digit",
    weekday: "short",
    year: "numeric",
  });
}

/**
 * Return a formatted handover timestamp.
 */
export function handoverDateTimeLabel(value: unknown): string {
  return formatGermanDateTime(value, {
    day: "2-digit",
    fallback: "",
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
  });
}

/**
 * Return the display name of the assigned machine.
 */
export function machineName(handover: HandoverRecord): string {
  return handover.machine?.name || "";
}

/**
 * Build the searchable text blob for one handover card.
 */
function handoverSearchText(handover: HandoverRecord): string {
  return [
    handover.department,
    handover.area,
    machineName(handover),
    shiftLabel(handover.shift_type),
    productionStatusLabel(handover.production_status),
    machineStatusLabel(handover.machine_status),
    handover.problem_category,
    handover.content,
    handover.open_tasks,
    handover.machine_notes,
    handover.next_notes,
    handover.safety_notes,
    handover.material_notes,
    handover.cause,
    handover.action_taken,
    handover.follow_up_task,
    handover.responsible_employee,
    handover.involved_employees,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

/**
 * Return filtered handovers for the local search box.
 */
export function filterHandoversBySearch(
  handovers: readonly HandoverRecord[],
  search: string
): readonly HandoverRecord[] {
  const query = search.trim().toLowerCase();
  if (!query) return handovers;
  return handovers.filter((handover) => handoverSearchText(handover).includes(query));
}

/**
 * Calculate KPI counts for the current handover result set.
 */
export function handoverStats(handovers: readonly HandoverRecord[]): HandoverStats {
  return {
    open: handovers.filter((item) => item.status !== "completed").length,
    completed: handovers.filter((item) => item.status === "completed").length,
    safety: handovers.filter((item) => Boolean(item.safety_notes)).length,
    followup: handovers.filter((item) => Boolean(item.open_tasks || item.follow_up_task)).length,
  };
}

/**
 * Normalize unknown API errors for the handover UI.
 */
export function handoverErrorMessage(error: unknown, fallback = "Übergabe konnte nicht geladen werden."): string {
  return safeErrorMessage(error, fallback);
}
