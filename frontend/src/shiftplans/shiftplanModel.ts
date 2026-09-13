import { readStoredSession } from "../auth/session";
import type { ShiftPlan } from "./shiftplanTypes";

/**
 * Return whether the current stored user is a master admin.
 */
export function currentUserIsAdmin(): boolean {
  const user = readStoredSession().user;
  return user?.role === "master_admin";
}

/**
 * Return the best selected plan index for a plan list.
 */
export function selectedPlanIndexFor(plans: readonly ShiftPlan[], selectId?: number): number {
  if (selectId !== undefined) {
    const exactIndex = plans.findIndex((plan) => plan.id === selectId);
    if (exactIndex >= 0) return exactIndex;
  }
  const firstFilledIndex = plans.findIndex((plan) => Array.isArray(plan.entries) && plan.entries.length > 0);
  return firstFilledIndex >= 0 ? firstFilledIndex : 0;
}

/**
 * Replace or prepend a plan in the list while preserving current visibility.
 */
export function plansWithFallback(plans: readonly ShiftPlan[], fallbackPlan: ShiftPlan | null): ShiftPlan[] {
  if (!fallbackPlan || fallbackPlan.id === undefined || plans.some((plan) => plan.id === fallbackPlan.id)) {
    return [...plans];
  }
  return [fallbackPlan, ...plans];
}
