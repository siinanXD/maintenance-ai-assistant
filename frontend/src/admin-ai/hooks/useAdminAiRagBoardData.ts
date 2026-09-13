import { useEffect, useState } from "react";
import {
  loadAdminJobs,
  loadKnowledgeDocuments,
  loadKnowledgeNetwork,
  loadKnowledgeStatus,
  loadTrainingEntries,
  saveTrainingEntry,
  uploadKnowledgeDocument,
  type AdminAiPayload
} from "../adminAiApi";
import { numericId } from "../adminAiPromptFaqModel";
import {
  EMPTY_ADMIN_AI_RAG_BOARD_STATE,
  failedRagBoardState,
  knowledgeQueryString,
  networkQueryString,
  ragItems,
  trainingPayload,
  trainingQueryString,
  type AdminAiRagBoardFilters,
  type AdminAiRagBoardState,
  type AdminAiTrainingForm
} from "../adminAiRagBoardModel";
import { type AdminAiView } from "../adminAiViews";

/**
 * Load RAG Board data and expose filter and mutation helpers.
 */
export function useAdminAiRagBoardData(adminAiView: AdminAiView, canUseAdminAiApi: boolean) {
  const [ragBoardState, setRagBoardState] = useState<AdminAiRagBoardState>(
    EMPTY_ADMIN_AI_RAG_BOARD_STATE
  );

  useEffect(() => {
    if (adminAiView !== "rag_board" || !canUseAdminAiApi) return undefined;

    const controller = new AbortController();
    void refreshRagBoard(controller.signal);

    return () => {
      controller.abort();
    };
  }, [adminAiView, canUseAdminAiApi, ragBoardState.filters]);

  /**
   * Load all React-owned RAG Board datasets with partial failure handling.
   */
  async function refreshRagBoard(signal?: AbortSignal): Promise<void> {
    const filters = ragBoardState.filters;
    setRagBoardState((currentState) => ({ ...currentState, errorMessage: "", isLoading: true }));
    const [statusResult, knowledgeResult, trainingResult, networkResult, jobsResult] =
      await Promise.allSettled([
        loadKnowledgeStatus(signal),
        loadKnowledgeDocuments(knowledgeQueryString(filters), signal),
        loadTrainingEntries(trainingQueryString(filters), signal),
        loadKnowledgeNetwork(networkQueryString(filters), signal),
        loadAdminJobs(signal)
      ]);

    if (signal?.aborted) return;

    const failedResult = [
      statusResult,
      knowledgeResult,
      trainingResult,
      networkResult,
      jobsResult
    ].find((result) => result.status === "rejected");

    setRagBoardState((currentState) => ({
      ...currentState,
      errorMessage:
        failedResult?.status === "rejected"
          ? failedRagBoardState(failedResult.reason).errorMessage
          : "",
      isLoading: false,
      jobs: jobsResult.status === "fulfilled" ? ragItems(jobsResult.value) : currentState.jobs,
      knowledge:
        knowledgeResult.status === "fulfilled" ? ragItems(knowledgeResult.value) : currentState.knowledge,
      knowledgeStatus:
        statusResult.status === "fulfilled" ? statusResult.value : currentState.knowledgeStatus,
      network: networkResult.status === "fulfilled" ? networkResult.value : currentState.network,
      training:
        trainingResult.status === "fulfilled" ? ragItems(trainingResult.value) : currentState.training
    }));
  }

  /**
   * Merge one RAG Board filter value and let the loading effect refresh the view.
   */
  function updateRagBoardFilter(key: keyof AdminAiRagBoardFilters, value: string): void {
    setRagBoardState((currentState) => ({
      ...currentState,
      filters: { ...currentState.filters, [key]: value }
    }));
  }

  /**
   * Run a RAG Board action and refresh the board afterwards.
   */
  async function runRagBoardAction(
    statusMessage: string,
    action: () => Promise<AdminAiPayload>
  ): Promise<void> {
    setRagBoardState((currentState) => ({
      ...currentState,
      errorMessage: "",
      isSaving: true,
      statusMessage
    }));
    try {
      await action();
      setRagBoardState((currentState) => ({
        ...currentState,
        isSaving: false,
        statusMessage: "RAG Board aktualisiert."
      }));
      await refreshRagBoard();
    } catch (error) {
      setRagBoardState((currentState) => ({
        ...currentState,
        errorMessage: failedRagBoardState(error).errorMessage,
        isSaving: false,
        statusMessage: ""
      }));
    }
  }

  /**
   * Save a manual training entry from the React editor.
   */
  async function handleSaveTraining(form: AdminAiTrainingForm): Promise<void> {
    const entryId = numericId(form.id);
    await runRagBoardAction("Training wird gespeichert...", () =>
      saveTrainingEntry(trainingPayload(form), entryId || undefined)
    );
    setRagBoardState((currentState) => ({
      ...currentState,
      trainingForm: EMPTY_ADMIN_AI_RAG_BOARD_STATE.trainingForm
    }));
  }

  /**
   * Upload a knowledge document from the React RAG Board.
   */
  async function handleKnowledgeUpload(form: HTMLFormElement): Promise<void> {
    const formData = new FormData(form);
    await runRagBoardAction("Dokument wird hochgeladen...", () => uploadKnowledgeDocument(formData));
    form.reset();
  }

  return {
    handleKnowledgeUpload,
    handleSaveTraining,
    ragBoardState,
    runRagBoardAction,
    setRagBoardState,
    updateRagBoardFilter
  };
}
