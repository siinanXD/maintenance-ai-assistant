import { useState } from "react";

import {
  createFaqEntry,
  runAiChat,
  submitAiFeedback,
  testPromptDryRun
} from "../adminAiApi";
import {
  EMPTY_ADMIN_AI_SOURCE_CHECK_STATE,
  failedSourceCheckState,
  sourceCheckChatPayload,
  sourceCheckDryRunPayload,
  sourceCheckDryRunState,
  sourceCheckFaqPayload,
  sourceCheckFeedbackPayload,
  sourceCheckFormPayload,
  sourceCheckLiveState,
  sourceCheckQuestion,
  type AdminAiSourceCheckState
} from "../adminAiSourceCheckModel";

/**
 * Manage Admin-AI source check state and actions.
 */
export function useAdminAiSourceCheckData() {
  const [sourceCheckState, setSourceCheckState] = useState<AdminAiSourceCheckState>(
    EMPTY_ADMIN_AI_SOURCE_CHECK_STATE
  );

  /**
   * Run a dry or live source test from the React-owned Source Check view.
   */
  async function handleSourceTestSubmit(form: HTMLFormElement, intent?: string): Promise<void> {
    const payload = sourceCheckFormPayload(form);
    const mode = intent || String(payload.mode || "dry");
    const question = sourceCheckQuestion(payload);

    setSourceCheckState((currentState) => ({
      ...currentState,
      errorMessage: "",
      isRunning: true,
      statusMessage: "Quellenprüfung wird ausgeführt..."
    }));

    try {
      if (mode !== "live") {
        const dryRunResult = await testPromptDryRun(sourceCheckDryRunPayload(payload));
        setSourceCheckState({
          ...sourceCheckDryRunState(dryRunResult, question),
          statusMessage: "Dry-run ausgeführt."
        });
        return;
      }

      const liveResult = await runAiChat(sourceCheckChatPayload(payload));
      setSourceCheckState({
        ...sourceCheckLiveState(liveResult, question),
        statusMessage: "Live-Quellenprüfung ausgeführt."
      });
    } catch (error) {
      setSourceCheckState((currentState) => ({
        ...currentState,
        errorMessage: failedSourceCheckState(error).errorMessage,
        isRunning: false,
        statusMessage: ""
      }));
    }
  }

  /**
   * Store feedback for the latest live Source Check result.
   */
  async function handleSourceFeedback(rating: string, comment?: string): Promise<void> {
    if (!sourceCheckState.latestTest || sourceCheckState.latestTest.mode !== "live") {
      setSourceCheckState((currentState) => ({
        ...currentState,
        errorMessage: "Keine Live-Quellenprüfung vorhanden."
      }));
      return;
    }

    setSourceCheckState((currentState) => ({
      ...currentState,
      errorMessage: "",
      isSaving: true,
      statusMessage: "Bewertung wird gespeichert..."
    }));

    try {
      await submitAiFeedback(
        sourceCheckFeedbackPayload(
          sourceCheckState.latestTest,
          rating,
          comment || "Bewertung aus KI-Admin Quellenprüfung"
        )
      );
      setSourceCheckState((currentState) => ({
        ...currentState,
        isSaving: false,
        statusMessage:
          rating === "not_helpful" && comment
            ? "Fehlende Quelle als negatives Feedback markiert."
            : "Quellenprüfung bewertet."
      }));
    } catch (error) {
      setSourceCheckState((currentState) => ({
        ...currentState,
        errorMessage: failedSourceCheckState(error).errorMessage,
        isSaving: false,
        statusMessage: ""
      }));
    }
  }

  /**
   * Create a FAQ draft from the latest live Source Check result.
   */
  async function handleCreateSourceFaq(): Promise<void> {
    if (!sourceCheckState.latestTest || sourceCheckState.latestTest.mode !== "live") {
      setSourceCheckState((currentState) => ({
        ...currentState,
        errorMessage: "Keine Live-Quellenprüfung vorhanden."
      }));
      return;
    }

    setSourceCheckState((currentState) => ({
      ...currentState,
      errorMessage: "",
      isSaving: true,
      statusMessage: "FAQ-Entwurf wird erstellt..."
    }));

    try {
      await createFaqEntry(sourceCheckFaqPayload(sourceCheckState.latestTest));
      setSourceCheckState((currentState) => ({
        ...currentState,
        isSaving: false,
        statusMessage: "FAQ-Entwurf aus der Testfrage erstellt."
      }));
    } catch (error) {
      setSourceCheckState((currentState) => ({
        ...currentState,
        errorMessage: failedSourceCheckState(error).errorMessage,
        isSaving: false,
        statusMessage: ""
      }));
    }
  }

  return {
    handleCreateSourceFaq,
    handleSourceFeedback,
    handleSourceTestSubmit,
    setSourceCheckState,
    sourceCheckState
  };
}
