import { createContext, useMemo, type ReactNode } from "react";

import { legacyPermissionKeyFor } from "../app/runtimeBridge";
import { canViewStoredDashboard } from "./permissions";
import { useAuthContext } from "./AuthProvider";
import type { MaintenanceUser } from "./session";

type PermissionProviderValue = {
  readonly canView: (featureKey: string) => boolean;
  readonly canWrite: (featureKey: string) => boolean;
  readonly permissionKeyFor: (featureKey: string) => string;
};

const PermissionContext = createContext<PermissionProviderValue | null>(null);

/**
 * Return one stored permission object for a feature or dashboard key.
 */
function storedPermission(user: MaintenanceUser | null, featureKey: string): { readonly can_write?: boolean } {
  if (user?.role === "master_admin") return { can_write: true };
  const permission = user?.permissions?.[legacyPermissionKeyFor(featureKey)];
  return typeof permission === "object" && permission !== null && !Array.isArray(permission)
    ? permission
    : {};
}

/**
 * Provide permission helpers backed by the existing auth and feature-registry contracts.
 */
export function PermissionProvider({ children }: { readonly children: ReactNode }): ReactNode {
  const { user } = useAuthContext();
  const value = useMemo<PermissionProviderValue>(() => ({
    canView: (featureKey) => canViewStoredDashboard(user, legacyPermissionKeyFor(featureKey)),
    canWrite: (featureKey) => Boolean(storedPermission(user, featureKey).can_write),
    permissionKeyFor: legacyPermissionKeyFor
  }), [user]);

  return <PermissionContext.Provider value={value}>{children}</PermissionContext.Provider>;
}

