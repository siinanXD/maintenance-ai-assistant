import { useEffect, useState } from "react";
import {
  loadAdminAiKnowledgeGaps,
  loadAdminAiSummary,
  loadAdminJobs,
  loadAiObservability,
  loadAiStatus,
  loadOperationsHealth,
  loadRetrievalDebug,
  loadRetrievalTelemetry,
  type AdminAiPayload
} from "../adminAiApi";
import {
  EMPTY_ADMIN_AI_TECHNICAL_STATE,
  failedTechnicalState,
  observabilityQueryString,
  retrievalDebugQueryString,
  technicalItems,
  type AdminAiTechnicalFilters,
  type AdminAiTechnicalState
} from "../adminAiTechnicalModel";
import { type AdminAiView } from "../adminAiViews";

/**
 * Load Admin-AI technical diagnostics and expose action helpers.
 */
export function useAdminAiTechnicalData(adminAiView: AdminAiView, canUseAdminAiApi: boolean) {
  const [technicalState, setTechnicalState] = useState<AdminAiTechnicalState>(
    EMPTY_ADMIN_AI_TECHNICAL_STATE
  );

  useEffect(() => {
    if (adminAiView !== "technical" || !canUseAdminAiApi) return undefined;

    const controller = new AbortController();
    void refreshTechnical(controller.signal);

    return () => {
      controller.abort();
    };
  }, [adminAiView, canUseAdminAiApi, technicalState.filters]);

  /**
   * Load all React-owned Technical datasets with partial failure handling.
   */
  async function refreshTechnical(signal?: AbortSignal): Promise<void> {
    const filters = technicalState.filters;
    setTechnicalState((currentState) => ({ ...currentState, errorMessage: "", isLoading: true }));
    const [
      telemetryResult,
      debugResult,
      observabilityResult,
      gapsResult,
      jobsResult,
      operationsResult,
      summaryResult,
      aiStatusResult
    ] =
      await Promise.allSettled([
        loadRetrievalTelemetry(signal),
        loadRetrievalDebug(retrievalDebugQueryString(filters), signal),
        loadAiObservability(observabilityQueryString(), signal),
        loadAdminAiKnowledgeGaps(signal),
        loadAdminJobs(signal),
        loadOperationsHealth(signal),
        loadAdminAiSummary(signal),
        loadAiStatus(signal)
      ]);

    if (signal?.aborted) return;

    const failedResult = [
      telemetryResult,
      debugResult,
      observabilityResult,
      gapsResult,
      jobsResult,
      operationsResult,
      summaryResult,
      aiStatusResult
    ].find((result) => result.status === "rejected");
    const observability =
      observabilityResult.status === "fulfilled"
        ? observabilityResult.value
        : technicalState.observability || {};
    const gaps =
      gapsResult.status === "fulfilled"
        ? technicalItems(gapsResult.value)
        : technicalItems(observability.knowledge_gaps);

    setTechnicalState((currentState) => ({
      ...currentState,
      aiStatus: aiStatusResult.status === "fulfilled" ? aiStatusResult.value : currentState.aiStatus,
      errorMessage:
        failedResult?.status === "rejected"
          ? failedTechnicalState(failedResult.reason).errorMessage
          : "",
      isLoading: false,
      jobs: jobsResult.status === "fulfilled" ? technicalItems(jobsResult.value) : currentState.jobs,
      observability: { ...observability, knowledge_gaps: gaps },
      operations:
        operationsResult.status === "fulfilled" ? operationsResult.value : currentState.operations,
      retrievalDebug:
        debugResult.status === "fulfilled" ? technicalItems(debugResult.value) : currentState.retrievalDebug,
      summary: summaryResult.status === "fulfilled" ? summaryResult.value : currentState.summary,
      telemetry: telemetryResult.status === "fulfilled" ? telemetryResult.value : currentState.telemetry
    }));
  }

  /**
   * Merge one Technical filter and let the loading effect refresh the view.
   */
  function updateTechnicalFilter(key: keyof AdminAiTechnicalFilters, value: string): void {
    setTechnicalState((currentState) => ({
      ...currentState,
      filters: { ...currentState.filters, [key]: value }
    }));
  }

  /**
   * Run a Technical action and refresh diagnostics afterwards.
   */
  async function runTechnicalAction(
    statusMessage: string,
    action: () => Promise<AdminAiPayload>
  ): Promise<void> {
    setTechnicalState((currentState) => ({
      ...currentState,
      errorMessage: "",
      isSaving: true,
      statusMessage
    }));
    try {
      await action();
      setTechnicalState((currentState) => ({
        ...currentState,
        isSaving: false,
        statusMessage: "Technische Diagnose aktualisiert."
      }));
      await refreshTechnical();
    } catch (error) {
      setTechnicalState((currentState) => ({
        ...currentState,
        errorMessage: failedTechnicalState(error).errorMessage,
        isSaving: false,
        statusMessage: ""
      }));
    }
  }

  return {
    refreshTechnical,
    runTechnicalAction,
    technicalState,
    updateTechnicalFilter
  };
}
