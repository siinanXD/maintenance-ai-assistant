import { useEffect, useState } from "react";
import {
  loadAdminAiChats,
  loadAdminAiEvents,
  loadAdminAiSummary,
  loadAiStatus,
  loadOperationsHealth,
  payloadItems
} from "../adminAiApi";
import {
  EMPTY_ADMIN_AI_OVERVIEW_STATE,
  failedOverviewState,
  type AdminAiOverviewLoadState
} from "../adminAiOverviewModel";
import { type AdminAiView } from "../adminAiViews";

/**
 * Load and expose Admin-AI overview data.
 */
export function useAdminAiOverviewData(adminAiView: AdminAiView, canUseAdminAiApi: boolean) {
  const [overviewState, setOverviewState] = useState<AdminAiOverviewLoadState>(
    EMPTY_ADMIN_AI_OVERVIEW_STATE
  );
  const [overviewEventError, setOverviewEventError] = useState("");
  const [overviewChatQuery, setOverviewChatQuery] = useState("");

  useEffect(() => {
    if (adminAiView !== "overview" || !canUseAdminAiApi) return undefined;

    const controller = new AbortController();

    /**
     * Load all React-owned Admin-AI overview widgets without blocking the page on partial errors.
     */
    async function loadOverview(): Promise<void> {
      setOverviewState((currentState) => ({ ...currentState, isLoading: true, errorMessage: "" }));
      const [
        aiStatusResult,
        summaryResult,
        operationsResult,
        eventsResult,
        chatsResult
      ] = await Promise.allSettled([
        loadAiStatus(controller.signal),
        loadAdminAiSummary(controller.signal),
        loadOperationsHealth(controller.signal),
        loadAdminAiEvents(overviewEventError, controller.signal),
        loadAdminAiChats(overviewChatQuery, controller.signal)
      ]);

      if (controller.signal.aborted) return;

      const failedResult = [aiStatusResult, summaryResult, operationsResult, eventsResult, chatsResult].find(
        (result) => result.status === "rejected"
      );

      setOverviewState((currentState) => ({
        aiStatus: aiStatusResult.status === "fulfilled" ? aiStatusResult.value : null,
        chats: chatsResult.status === "fulfilled" ? payloadItems(chatsResult.value) : currentState.chats,
        events: eventsResult.status === "fulfilled" ? payloadItems(eventsResult.value) : currentState.events,
        summary: summaryResult.status === "fulfilled" ? summaryResult.value : null,
        operations: operationsResult.status === "fulfilled" ? operationsResult.value : null,
        errorMessage:
          failedResult?.status === "rejected"
            ? failedOverviewState(failedResult.reason).errorMessage
            : "",
        isLoading: false
      }));
    }

    void loadOverview();

    return () => {
      controller.abort();
    };
  }, [adminAiView, canUseAdminAiApi, overviewChatQuery, overviewEventError]);

  return {
    overviewChatQuery,
    overviewEventError,
    overviewState,
    setOverviewChatQuery,
    setOverviewEventError
  };
}
