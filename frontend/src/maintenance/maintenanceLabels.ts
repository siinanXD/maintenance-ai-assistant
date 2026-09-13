import type { DueState, MaintenancePlan, PlanDraft, RecordResult } from "./maintenanceTypes";

export const DUE_STATE_LABELS: Readonly<Record<DueState, string>> = {
  overdue: "Überfällig",
  due_soon: "In 30 Tagen fällig",
  ok: "Im Plan",
  inactive: "Pausiert"
};

export const RESULT_LABELS: Readonly<Record<RecordResult, string>> = {
  passed: "Bestanden",
  defects: "Mit Mängeln",
  failed: "Nicht bestanden"
};

const DATE_FORMAT = new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });

/**
 * Format an ISO date as DD.MM.YYYY.
 */
export function formatPlanDate(value: string | null | undefined): string {
  if (!value) return "–";
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  return DATE_FORMAT.format(new Date(year, month - 1, day));
}

/**
 * Return a human interval such as "jährlich" or "alle 14 Tage".
 */
export function intervalLabel(days: number): string {
  if (days === 365) return "jährlich";
  if (days === 182 || days === 183) return "halbjährlich";
  if (days === 90 || days === 91) return "vierteljährlich";
  if (days === 30 || days === 31) return "monatlich";
  if (days === 7) return "wöchentlich";
  if (days === 1) return "täglich";
  return `alle ${days} Tage`;
}

/**
 * Return days until the next due date (negative when overdue).
 */
export function daysUntil(value: string): number {
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  const due = new Date(year, month - 1, day).getTime();
  const today = new Date();
  const midnight = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  return Math.round((due - midnight) / 86_400_000);
}

/**
 * Return today's date in ISO format using the local calendar.
 */
export function todayIso(): string {
  const today = new Date();
  return [today.getFullYear(), String(today.getMonth() + 1).padStart(2, "0"), String(today.getDate()).padStart(2, "0")].join("-");
}

/**
 * Return an empty plan draft; inspections default to a yearly interval.
 */
export function emptyPlanDraft(): PlanDraft {
  return {
    title: "",
    kind: "inspection",
    legal_basis: "",
    description: "",
    interval_days: "365",
    next_due_date: todayIso(),
    machine_id: "",
    priority: "normal"
  };
}

/**
 * Convert a plan into an editable draft.
 */
export function draftFromPlan(plan: MaintenancePlan): PlanDraft {
  return {
    title: plan.title,
    kind: plan.kind,
    legal_basis: plan.legal_basis,
    description: plan.description,
    interval_days: String(plan.interval_days),
    next_due_date: plan.next_due_date,
    machine_id: plan.machine_id ? String(plan.machine_id) : "",
    priority: plan.priority
  };
}
