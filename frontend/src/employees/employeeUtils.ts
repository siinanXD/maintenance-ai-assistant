import { authRuntime } from "../app/runtimeBridge";
import { readStoredSession } from "../auth/session";
import { triggerBrowserDownload } from "../utils/download";
import { safeErrorMessage } from "../utils/errors";
import type { Employee, EmployeeDraft } from "./employeeTypes";

export const EMPTY_EMPLOYEE_DRAFT: EmployeeDraft = {
  personnel_number: "",
  name: "",
  birth_date: "",
  city: "",
  street: "",
  postal_code: "",
  department: "",
  shift_model: "gleitzeit",
  current_shift: "",
  team: "",
  salary_group: "",
  favorite_machine: "",
  qualifications: ""
};

/**
 * Convert an employee into the edit form draft.
 */
export function draftFromEmployee(employee: Employee | null): EmployeeDraft {
  if (!employee) return { ...EMPTY_EMPLOYEE_DRAFT };
  return {
    personnel_number: employee.personnel_number || "",
    name: employee.name || "",
    birth_date: employee.birth_date || "",
    city: employee.city || "",
    street: employee.street || "",
    postal_code: employee.postal_code || "",
    department: employee.department || "",
    shift_model: employee.shift_model || "gleitzeit",
    current_shift: employee.current_shift || "",
    team: employee.team ? String(employee.team) : "",
    salary_group: employee.salary_group || "",
    favorite_machine: employee.favorite_machine || "",
    qualifications: employee.qualifications || ""
  };
}

/**
 * Return a safe user-facing error message.
 */
export function employeeErrorMessage(error: unknown): string {
  return safeErrorMessage(error, "Mitarbeiteraktion konnte nicht verarbeitet werden.");
}

/**
 * Return the current employee access level from the existing auth runtime or storage.
 */
function currentEmployeeAccessLevel(): string {
  const runtimeLevel = authRuntime()?.employeeAccessLevel?.();
  if (runtimeLevel) return runtimeLevel;

  const user = readStoredSession().user;
  if (user?.role === "master_admin") return "confidential";

  const permission = user?.permissions?.employees;
  if (typeof permission === "object" && permission !== null && !Array.isArray(permission)) {
    const level = (permission as { readonly employee_access_level?: unknown }).employee_access_level;
    return typeof level === "string" ? level : "none";
  }
  return "none";
}

/**
 * Return whether a user may manage confidential employee records.
 */
export function canManageEmployees(writable: boolean): boolean {
  const runtimeCanManage = authRuntime()?.canManageEmployees?.();
  if (typeof runtimeCanManage === "boolean") return runtimeCanManage;
  return writable && currentEmployeeAccessLevel() === "confidential";
}

/**
 * Return searchable plain text for one employee card.
 */
export function employeeSearchText(employee: Employee): string {
  return [
    employee.name,
    employee.personnel_number,
    employee.department,
    employee.team ? `Team ${employee.team}` : "",
    employee.shift_model,
    employee.current_shift,
    employee.qualifications,
    employee.favorite_machine
  ].filter(Boolean).join(" ").toLowerCase();
}

/**
 * Split comma-separated qualifications into badge labels.
 */
export function qualificationLabels(value: string | undefined): string[] {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

/**
 * Trigger a browser download for one employee document.
 */
export function triggerEmployeeDocumentDownload(downloadUrl: string | undefined, filename: string | undefined): boolean {
  return triggerBrowserDownload(downloadUrl, filename || "mitarbeiter-dokument");
}
