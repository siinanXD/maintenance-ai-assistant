import { readStoredSession, type MaintenanceUser } from "./session";
import { authRuntime } from "../app/runtimeBridge";

export type MaintenanceAuthRuntime = {
  readonly clearSession?: (options?: { readonly redirect?: boolean }) => void;
  readonly canManageEmployees?: () => boolean;
  readonly canView?: (dashboard: string) => boolean;
  readonly canWrite?: (dashboard: string) => boolean;
  readonly destinationForUserOrNext?: (user: MaintenanceUser, nextPath: string | null) => string;
  readonly employeeAccessLevel?: () => string;
  readonly ensureReady?: () => Promise<MaintenanceUser | null>;
  readonly logout?: () => Promise<void>;
  readonly refreshUser?: () => Promise<MaintenanceUser | null>;
  readonly token?: () => string | null;
  readonly user?: () => MaintenanceUser | null;
};

declare global {
  interface Window {
    readonly maintenanceAuth?: MaintenanceAuthRuntime;
  }
}

/**
 * Return a stored dashboard permission for early React module execution.
 */
function storedPermissionFor(dashboard: string): { readonly can_view?: boolean; readonly can_write?: boolean } {
  const session = readStoredSession();
  const user = session.user;

  if (user?.role === "master_admin") {
    return { can_view: true, can_write: true };
  }

  const permission = user?.permissions?.[dashboard];
  return typeof permission === "object" && permission !== null && !Array.isArray(permission)
    ? permission
    : {};
}

/**
 * Return whether a user may view a dashboard area from stored permissions.
 */
export function canViewStoredDashboard(user: MaintenanceUser | null, dashboard: string): boolean {
  if (user?.role === "master_admin") {
    return true;
  }
  const permission = user?.permissions?.[dashboard];
  return (
    typeof permission === "object"
    && permission !== null
    && !Array.isArray(permission)
    && Boolean((permission as { readonly can_view?: boolean }).can_view)
  );
}

/**
 * Return whether the current user may view a dashboard area.
 */
export function canViewDashboard(dashboard: string): boolean {
  const maintenanceAuth = authRuntime();
  if (maintenanceAuth && typeof maintenanceAuth.canView === "function") {
    return maintenanceAuth.canView(dashboard);
  }

  return Boolean(storedPermissionFor(dashboard).can_view);
}

/**
 * Return whether the current user may write to a dashboard area.
 */
export function canWriteDashboard(dashboard: string): boolean {
  const maintenanceAuth = authRuntime();
  if (maintenanceAuth && typeof maintenanceAuth.canWrite === "function") {
    return maintenanceAuth.canWrite(dashboard);
  }

  return Boolean(storedPermissionFor(dashboard).can_write);
}
