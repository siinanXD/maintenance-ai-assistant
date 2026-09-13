import { useEffect, useState } from "react";
import {
  loadAdminAiSummary,
  loadAdminAiUserCosts,
  loadRetrievalTelemetry
} from "../adminAiApi";
import {
  EMPTY_ADMIN_AI_EFFECTIVENESS_STATE,
  failedEffectivenessState,
  userCostRows,
  type AdminAiEffectivenessState
} from "../adminAiEffectivenessModel";
import { type AdminAiView } from "../adminAiViews";

/**
 * Load and expose Admin-AI effectiveness data.
 */
export function useAdminAiEffectivenessData(adminAiView: AdminAiView, canUseAdminAiApi: boolean) {
  const [effectivenessState, setEffectivenessState] = useState<AdminAiEffectivenessState>(
    EMPTY_ADMIN_AI_EFFECTIVENESS_STATE
  );

  useEffect(() => {
    if (adminAiView !== "effectiveness" || !canUseAdminAiApi) return undefined;

    const controller = new AbortController();

    /**
     * Load React-owned Admin-AI effectiveness widgets with partial failure handling.
     */
    async function loadEffectiveness(): Promise<void> {
      setEffectivenessState((currentState) => ({
        ...currentState,
        errorMessage: "",
        isLoading: true
      }));
      const [summaryResult, userCostsResult, telemetryResult] = await Promise.allSettled([
        loadAdminAiSummary(controller.signal),
        loadAdminAiUserCosts(controller.signal),
        loadRetrievalTelemetry(controller.signal)
      ]);

      if (controller.signal.aborted) return;

      const failedResult = [summaryResult, userCostsResult, telemetryResult].find(
        (result) => result.status === "rejected"
      );
      const userCostsPayload = userCostsResult.status === "fulfilled" ? userCostsResult.value : null;

      setEffectivenessState({
        summary: summaryResult.status === "fulfilled" ? summaryResult.value : null,
        telemetry: telemetryResult.status === "fulfilled" ? telemetryResult.value : null,
        userCosts: userCostRows(userCostsPayload),
        errorMessage:
          failedResult?.status === "rejected"
            ? failedEffectivenessState(failedResult.reason).errorMessage
            : "",
        isLoading: false
      });
    }

    void loadEffectiveness();

    return () => {
      controller.abort();
    };
  }, [adminAiView, canUseAdminAiApi]);

  return { effectivenessState };
}
