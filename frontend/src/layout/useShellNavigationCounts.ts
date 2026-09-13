import { useEffect, useState } from "react";

import { apiRequest } from "../api/client";
import { canViewStoredDashboard } from "../auth/permissions";
import type { MaintenanceUser } from "../auth/session";
import type { ShellNavigationCounts } from "./shellNavigationTypes";

const EMPTY_NAVIGATION_COUNTS: ShellNavigationCounts = {
  errors: 0,
  tasks: 0
};

/**
 * Return true when a value is a plain API payload object.
 */
function isPayload(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Return a numeric total from paginated API responses or list payloads.
 */
function totalFromPayload(payload: unknown): number {
  if (isPayload(payload)) {
    const pagination = payload.pagination;
    if (isPayload(pagination) && Number.isFinite(Number(pagination.total))) {
      return Number(pagination.total);
    }

    const data = payload.data;
    if (isPayload(data)) {
      const dataPagination = data.pagination;
      if (isPayload(dataPagination) && Number.isFinite(Number(dataPagination.total))) {
        return Number(dataPagination.total);
      }
    }

    if (Array.isArray(data)) {
      return data.length;
    }
  }

  return Array.isArray(payload) ? payload.length : 0;
}

/**
 * Load React-owned sidebar counters for task and active incident navigation badges.
 */
export function useShellNavigationCounts(user: MaintenanceUser | null): ShellNavigationCounts {
  const [counts, setCounts] = useState<ShellNavigationCounts>(EMPTY_NAVIGATION_COUNTS);

  useEffect(() => {
    const controller = new AbortController();

    /**
     * Fetch visible shell counters from the existing list APIs.
     */
    async function loadCounts(): Promise<void> {
      if (!user) {
        setCounts(EMPTY_NAVIGATION_COUNTS);
        return;
      }

      const canViewTasks = canViewStoredDashboard(user, "tasks");
      const canViewErrors = canViewStoredDashboard(user, "errors");

      const [tasksResult, errorsResult] = await Promise.allSettled([
        // Same definition as the cockpit KPI "Offene Aufgaben": only status open,
        // not every task ever created (which counted completed work as well).
        canViewTasks
          ? apiRequest<unknown>("/api/v1/tasks?limit=1&status=open", { signal: controller.signal })
          : Promise.resolve([]),
        canViewErrors
          ? apiRequest<unknown>("/api/v1/errors?limit=1&active=1", { signal: controller.signal })
          : Promise.resolve([])
      ]);

      if (controller.signal.aborted) return;

      if (tasksResult.status === "rejected") {
        console.warn("Aufgabenzähler konnte nicht geladen werden.", tasksResult.reason);
      }
      if (errorsResult.status === "rejected") {
        console.warn("Störungszähler konnte nicht geladen werden.", errorsResult.reason);
      }

      setCounts({
        errors: errorsResult.status === "fulfilled" ? totalFromPayload(errorsResult.value) : 0,
        tasks: tasksResult.status === "fulfilled" ? totalFromPayload(tasksResult.value) : 0
      });
    }

    void loadCounts();

    return () => controller.abort();
  }, [user]);

  return counts;
}
