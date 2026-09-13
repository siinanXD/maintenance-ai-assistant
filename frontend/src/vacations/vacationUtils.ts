import { readStoredSession } from "../auth/session";
import { todayIsoDate } from "../utils/date";
import { safeErrorMessage } from "../utils/errors";
import type {
  Employee,
  MaintenanceUser,
  VacationDraft,
  VacationRequest,
  VacationSummary
} from "./vacationTypes";

export const EMPTY_VACATION_DRAFT: VacationDraft = {
  employeeId: "",
  startDate: "",
  endDate: "",
  shiftType: "",
  representativeEmployeeId: "",
  reason: "",
  notes: ""
};

/**
 * Return a safe user-facing error message.
 */
export function vacationErrorMessage(error: unknown): string {
  return safeErrorMessage(error, "Urlaubsaktion konnte nicht verarbeitet werden.");
}

/**
 * Return the current year as a string for the year selector.
 */
export function currentVacationYear(): string {
  return String(new Date().getFullYear());
}

/**
 * Return the vacation year selector options.
 */
export function vacationYearOptions(): string[] {
  const year = new Date().getFullYear();
  return [year - 1, year, year + 1, year + 2].map(String);
}

/**
 * Return today's date in HTML date-input format.
 */
export function todayDateInputValue(): string {
  return todayIsoDate();
}

/**
 * Format an ISO date for compact German display.
 */
export function formatVacationDate(value: string | undefined): string {
  if (!value) return "-";
  const parts = value.split("-");
  return parts.length === 3 ? `${parts[2]}.${parts[1]}.${parts[0]}` : value;
}

/**
 * Count workdays between two ISO dates.
 */
export function countVacationWorkdays(startDate: string, endDate: string): number | null {
  if (!startDate || !endDate || endDate < startDate) return null;
  let count = 0;
  const day = new Date(`${startDate}T00:00:00`);
  const last = new Date(`${endDate}T00:00:00`);
  while (day <= last) {
    if (day.getDay() >= 1 && day.getDay() <= 5) count += 1;
    day.setDate(day.getDate() + 1);
  }
  return count;
}

/**
 * Return a human label for one shift type.
 */
export function vacationShiftLabel(value: string | undefined): string {
  const labels: Record<string, string> = {
    Frueh: "Früh",
    Spaet: "Spät",
    Nacht: "Nacht",
    Tag: "Tagdienst",
    Alle: "Alle Schichten"
  };
  return labels[value || ""] || "Keine feste Schicht";
}

/**
 * Return a human label for one vacation status.
 */
export function vacationStatusLabel(status: string | undefined): string {
  return {
    approved: "Genehmigt",
    rejected: "Abgelehnt",
    pending: "Ausstehend",
    cancelled: "Storniert"
  }[status || ""] || status || "-";
}

/**
 * Return a human label for an impact level.
 */
export function vacationImpactLabel(level: string | undefined): string {
  if (level === "critical") return "Kritisch";
  if (level === "warning") return "Warnung";
  return "OK";
}

/**
 * Return the stored user if the API user cannot be loaded yet.
 */
export function storedMaintenanceUser(): MaintenanceUser | null {
  return readStoredSession().user as MaintenanceUser | null;
}

/**
 * Return a user's department name.
 */
function userDepartmentName(user: MaintenanceUser | null): string {
  const department = user?.department;
  if (typeof department === "string") return department;
  return department?.name || "";
}

/**
 * Return whether the current user may decide a vacation request.
 */
export function canDecideVacation(user: MaintenanceUser | null, request: VacationRequest): boolean {
  if (!user) return false;
  if (user.role === "master_admin") return true;
  const employeesPermission = user.permissions?.employees || {};
  const requestDepartment = request.employee?.department || request.department || "";
  return Boolean(employeesPermission.can_write && userDepartmentName(user) && requestDepartment === userDepartmentName(user));
}

/**
 * Return whether the current user may cancel a vacation request.
 */
export function canCancelVacation(user: MaintenanceUser | null, request: VacationRequest): boolean {
  if (!user || request.status === "cancelled") return false;
  if (user.role === "master_admin") return true;
  if (user.employee_id === request.employee_id) return true;
  return canDecideVacation(user, request);
}

/**
 * Return a validation message for the current draft.
 */
export function vacationValidationError(draft: VacationDraft, balance: VacationSummary | null): string {
  if (!draft.employeeId || !draft.startDate || !draft.endDate) return "";
  if (draft.endDate < draft.startDate) return "Enddatum darf nicht vor dem Startdatum liegen.";
  const days = countVacationWorkdays(draft.startDate, draft.endDate);
  if (!days) return "Im gewählten Zeitraum liegt kein Arbeitstag.";
  if (balance && days > Number(balance.available || 0)) {
    return "Der Antrag überschreitet den verfügbaren Resturlaub.";
  }
  return "";
}

/**
 * Return one employee label for select options.
 */
export function employeeOptionLabel(employee: Employee): string {
  return `${employee.name || employee.id}${employee.department ? ` (${employee.department})` : ""}`;
}

/**
 * Return true when a representative can be selected for the current employee.
 */
export function representativeAllowed(employee: Employee | null, representative: Employee): boolean {
  if (!employee) return true;
  return representative.id !== employee.id && representative.department === employee.department;
}

/**
 * Return text for the summary card department line.
 */
export function vacationSummaryMeta(summary: VacationSummary): string {
  return [
    summary.department || "Bereich offen",
    summary.current_shift || summary.shift_model || "",
    summary.team ? `Team ${summary.team}` : ""
  ].filter(Boolean).join(" · ");
}
