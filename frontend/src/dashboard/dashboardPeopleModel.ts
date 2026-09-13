import { type DashboardPayload } from "./dashboardApi";

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

