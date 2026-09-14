import { useAuthSession } from "../auth/useAuthSession";

/**
 * The Admin-AI API is restricted to master admins (Role.MASTER_ADMIN in the backend).
 */
export function useCanUseAdminAi(): boolean {
  return String(useAuthSession().user?.role || "").toLowerCase() === "master_admin";
}
