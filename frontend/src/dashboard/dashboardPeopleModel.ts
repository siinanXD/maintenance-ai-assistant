import { type DashboardPayload, type DashboardRuntimeData } from "./dashboardApi";

/**
 * Return a normalized text field from a dashboard payload.
 */
export function peopleText(payload: DashboardPayload | null | undefined, key: string, fallback = ""): string {
  const value = payload?.[key];
  return typeof value === "string" && value.trim() ? value : fallback;
}

/**
 * Return the dashboard attendance status for an employee.
 */
function employeeStatus(employee: DashboardPayload): string {
  const shift = peopleText(employee, "current_shift", peopleText(employee, "shift_model")).toLowerCase();
  if (shift.includes("urlaub") || shift.includes("frei")) return "Abwesend";
  if (!shift) return "Geplant";
  return "Anwesend";
}

/**
 * Return open or relevant vacation requests for people hints.
 */
export function relevantVacations(vacations: readonly DashboardPayload[]): readonly DashboardPayload[] {
  return vacations.filter((vacation) => peopleText(vacation, "status").toLowerCase() !== "rejected");
}

/**
 * Return absent employees for people hints.
 */
export function absentEmployees(employees: readonly DashboardPayload[]): readonly DashboardPayload[] {
  return employees.filter((employee) => employeeStatus(employee) === "Abwesend");
}

/**
 * Return a dashboard people KPI value.
 */
export function peopleStatusValue(data: DashboardRuntimeData): string {
  const vacations = relevantVacations(data.vacations);
  const absent = absentEmployees(data.employees);
  return String(vacations.length || absent.length || data.employees.length || "--");
}

/**
 * Return a dashboard people KPI meta label.
 */
export function peopleStatusMeta(data: DashboardRuntimeData): string {
  const vacations = relevantVacations(data.vacations);
  const absent = absentEmployees(data.employees);
  if (vacations.length) return `${vacations.length} offene Urlaubsanträge`;
  if (absent.length) return `${absent.length} abwesend`;
  return "Keine offenen Personalwarnungen";
}

/**
 * Return a dashboard shift KPI value based on loaded handovers.
 */
export function handoverStatusValue(data: DashboardRuntimeData): string {
  return data.handovers.length ? String(data.handovers.length) : "--";
}

/**
 * Return a dashboard shift KPI meta label based on loaded handovers.
 */
export function handoverStatusMeta(data: DashboardRuntimeData): string {
  return data.handovers.length ? `${data.handovers.length} Übergaben heute` : "Keine Übergabe heute";
}
