import { useAuthSession } from "../auth/useAuthSession";

type AdminAiRoleAccess = {
  readonly canUseAdminAiApi: boolean;
  readonly isTechnicalRole: boolean;
  readonly role: string;
};

const ADMIN_AI_API_ROLES = new Set(["master_admin"]);

/**
 * Mirror the backend Admin-AI API contract, which is protected by Role.MASTER_ADMIN.
 */
export function canUseAdminAiApi(role: string | undefined): boolean {
  return ADMIN_AI_API_ROLES.has(String(role || "").toLowerCase());
}

/**
 * Return whether the provided role may see technical AI diagnostics.
 */
function isTechnicalAiRole(role: string | undefined): boolean {
  return canUseAdminAiApi(role);
}

/**
 * Return the current AI admin role visibility flags from the stored auth session.
 */
export function useAdminAiRoleAccess(): AdminAiRoleAccess {
  const session = useAuthSession();
  const role = String(session.user?.role || "");

  return {
    canUseAdminAiApi: canUseAdminAiApi(role),
    isTechnicalRole: isTechnicalAiRole(role),
    role
  };
}
