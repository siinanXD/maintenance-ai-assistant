import {
  confirmAction,
  authRuntime,
  requestText
} from "../app/runtimeBridge";
import { formatGermanDateTime } from "../utils/date";
import { triggerBrowserDownload } from "../utils/download";
import { safeErrorMessage } from "../utils/errors";
import type { AdminPermission, AdminUser, PermissionSchema } from "./adminUserTypes";

export const ROLE_OPTIONS = [
  ["master_admin", "Master Admin"],
  ["it", "IT"],
  ["verwaltung", "Verwaltung"],
  ["instandhaltung", "Instandhaltung"],
  ["produktion", "Produktion"],
  ["personalabteilung", "Personalabteilung"]
] as const;

/**
 * Return a safe user-facing admin error message.
 */
export function adminUserErrorMessage(error: unknown): string {
  return safeErrorMessage(error, "Admin-Aktion konnte nicht verarbeitet werden.");
}

/**
 * Format an audit or backup timestamp.
 */
export function adminDateLabel(value: unknown): string {
  return formatGermanDateTime(value, { fallback: "-", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/**
 * Format bytes for the backup table.
 */
export function formatBytes(value: unknown): string {
  const bytes = Number(value || 0);
  if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

/**
 * Return a compact number label.
 */
export function compactNumber(value: unknown): string {
  const number = Number(value || 0);
  if (number >= 1000000) return `${(number / 1000000).toFixed(1)}M`;
  if (number >= 1000) return `${(number / 1000).toFixed(1)}k`;
  return String(number);
}

/**
 * Format a USD cost value.
 */
export function formatUsd(value: unknown): string {
  return `$${Number(value || 0).toFixed(4)}`;
}

/**
 * Format a ratio as a percent label.
 */
export function percentLabel(value: unknown): string {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

/**
 * Return a dashboard label from schema metadata.
 */
export function dashboardLabel(schema: PermissionSchema | null, dashboard: string): string {
  return schema?.dashboards.find((item) => item.key === dashboard)?.label || dashboard;
}

/**
 * Return an employee access label from schema metadata.
 */
export function employeeAccessLabel(schema: PermissionSchema | null, level: string): string {
  return schema?.employee_access_levels.find((item) => item.key === level)?.label || level;
}

/**
 * Return schema dashboards with a stable fallback.
 */
export function schemaDashboardKeys(schema: PermissionSchema | null): string[] {
  return schema?.dashboards.map((dashboard) => dashboard.key) || [];
}

/**
 * Return the role default permission for one dashboard.
 */
export function roleDefaultPermission(schema: PermissionSchema | null, role: string, dashboard: string): AdminPermission {
  return schema?.role_defaults?.[role]?.[dashboard] || {
    can_view: false,
    can_write: false,
    employee_access_level: "none"
  };
}

/**
 * Summarize a permission row for confirmation text.
 */
export function permissionSummary(schema: PermissionSchema | null, permission: AdminPermission): string {
  const parts = [];
  if (permission.can_view) parts.push("Anzeigen");
  if (permission.can_write) parts.push("Bearbeiten");
  if (permission.employee_access_level && permission.employee_access_level !== "none") {
    parts.push(employeeAccessLabel(schema, permission.employee_access_level));
  }
  return parts.length ? parts.join(", ") : "Keine Rechte";
}

/**
 * Return whether two permissions differ.
 */
function permissionChanged(left: AdminPermission, right: AdminPermission): boolean {
  return Boolean(left.can_view) !== Boolean(right.can_view)
    || Boolean(left.can_write) !== Boolean(right.can_write)
    || (left.employee_access_level || "none") !== (right.employee_access_level || "none");
}

/**
 * Build confirmation lines for edited permissions.
 */
export function permissionChangeSummary(
  schema: PermissionSchema | null,
  user: AdminUser,
  permissions: Record<string, AdminPermission>
): string[] {
  return schemaDashboardKeys(schema)
    .map((dashboard) => {
      const before = user.permissions?.[dashboard] || { can_view: false, can_write: false, employee_access_level: "none" };
      const after = permissions[dashboard] || { can_view: false, can_write: false, employee_access_level: "none" };
      if (!permissionChanged(before, after)) return "";
      return `${dashboardLabel(schema, dashboard)}: ${permissionSummary(schema, before)} -> ${permissionSummary(schema, after)}`;
    })
    .filter(Boolean);
}

/**
 * Request confirmation through the shared app dialog.
 */
export async function confirmAdminAction(title: string, message: string, confirmText = "Bestätigen"): Promise<boolean> {
  return confirmAction({ title, message, confirmText });
}

/**
 * Request password text through the shared app dialog.
 */
export async function requestPassword(title: string, message: string): Promise<string | null> {
  return requestText({
    title,
    message,
    label: "Neues Passwort",
    inputType: "password",
    required: true,
    confirmText: "Speichern"
  });
}

/**
 * Trigger a backup download.
 */
export function downloadBackup(downloadUrl: string | undefined, filename: string): boolean {
  return triggerBrowserDownload(downloadUrl, filename);
}

/**
 * Refresh the existing auth runtime when the current user changes.
 */
export async function refreshCurrentUserIfNeeded(updatedUserId: number, currentUserId: number | undefined): Promise<void> {
  const runtime = authRuntime();
  if (updatedUserId === currentUserId && runtime?.refreshUser) {
    await runtime.refreshUser();
  }
}
