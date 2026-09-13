import { useEffect, useState } from "react";
import {
  approveFaqEntry,
  createFaqEntry,
  createPromptVersion,
  loadFaqEntries,
  loadFaqSuggestions,
  loadPromptTemplates,
  loadResponseSnippets
} from "../adminAiApi";
import {
  EMPTY_ADMIN_AI_PROMPT_FAQ_STATE,
  failedPromptFaqState,
  faqEntries,
  faqSuggestions,
  formPayload,
  numericId,
  promptTemplates,
  responseSnippets,
  settledPayload,
  type AdminAiFaqEntry,
  type AdminAiPromptFaqState
} from "../adminAiPromptFaqModel";
import { type AdminAiView } from "../adminAiViews";

/**
 * Load Prompt & FAQ data and expose write handlers.
 */
export function useAdminAiPromptFaqData(adminAiView: AdminAiView, canUseAdminAiApi: boolean) {
  const [promptFaqState, setPromptFaqState] = useState<AdminAiPromptFaqState>(
    EMPTY_ADMIN_AI_PROMPT_FAQ_STATE
  );

  useEffect(() => {
    if (adminAiView !== "prompt_faq" || !canUseAdminAiApi) return undefined;

    const controller = new AbortController();
    void refreshPromptFaq(controller.signal);

    return () => {
      controller.abort();
    };
  }, [adminAiView, canUseAdminAiApi]);

  /**
   * Load React-owned Prompt & FAQ data with partial failure handling.
   */
  async function refreshPromptFaq(signal?: AbortSignal): Promise<void> {
    setPromptFaqState((currentState) => ({
      ...currentState,
      errorMessage: "",
      isLoading: true
    }));
    const [promptsResult, faqResult, suggestionsResult, snippetsResult] = await Promise.allSettled([
      loadPromptTemplates(signal),
      loadFaqEntries(signal),
      loadFaqSuggestions(signal),
      loadResponseSnippets(signal)
    ]);

    if (signal?.aborted) return;

    const promptPayload = settledPayload(promptsResult);
    const faqPayload = settledPayload(faqResult);
    const suggestionsPayload = settledPayload(suggestionsResult);
    const snippetsPayload = settledPayload(snippetsResult);
    const suggestionPayload = faqSuggestions(suggestionsPayload);
    const failedResult = [promptsResult, faqResult, suggestionsResult, snippetsResult].find(
      (result) => result.status === "rejected"
    );

    setPromptFaqState((currentState) => ({
      ...currentState,
      errorMessage:
        failedResult?.status === "rejected"
          ? failedPromptFaqState(failedResult.reason).errorMessage
          : "",
      faqEntries: faqEntries(faqPayload),
      frequentQuestions: suggestionPayload.frequentQuestions,
      isLoading: false,
      knowledgeGaps: suggestionPayload.knowledgeGaps,
      prompts: promptTemplates(promptPayload),
      responseSnippets: responseSnippets(snippetsPayload)
    }));
  }

  /**
   * Create a prompt version from the visible Prompt & FAQ form.
   */
  async function handlePromptVersionSubmit(form: HTMLFormElement): Promise<void> {
    const payload = formPayload(form);
    const templateId = numericId(payload.template_id);
    if (!templateId) {
      setPromptFaqState((currentState) => ({
        ...currentState,
        promptFormStatus: "Bitte Workflow auswählen."
      }));
      return;
    }

    setPromptFaqState((currentState) => ({ ...currentState, isSaving: true, promptFormStatus: "Speichert..." }));
    try {
      await createPromptVersion(templateId, payload);
      form.reset();
      setPromptFaqState((currentState) => ({
        ...currentState,
        promptFormStatus: "Entwurf gespeichert",
        statusMessage: "Prompt-Entwurf gespeichert."
      }));
      await refreshPromptFaq();
    } catch (error) {
      setPromptFaqState((currentState) => ({
        ...currentState,
        errorMessage: failedPromptFaqState(error).errorMessage
      }));
    } finally {
      setPromptFaqState((currentState) => ({ ...currentState, isSaving: false }));
    }
  }

  /**
   * Create a manual FAQ draft from the visible Prompt & FAQ form.
   */
  async function handleFaqSubmit(form: HTMLFormElement): Promise<void> {
    const payload = {
      ...formPayload(form),
      source: "manual",
      status: "draft"
    };
    setPromptFaqState((currentState) => ({ ...currentState, isSaving: true }));
    try {
      await createFaqEntry(payload);
      form.reset();
      setPromptFaqState((currentState) => ({
        ...currentState,
        statusMessage: "FAQ-Entwurf gespeichert."
      }));
      await refreshPromptFaq();
    } catch (error) {
      setPromptFaqState((currentState) => ({
        ...currentState,
        errorMessage: failedPromptFaqState(error).errorMessage
      }));
    } finally {
      setPromptFaqState((currentState) => ({ ...currentState, isSaving: false }));
    }
  }

  /**
   * Approve one FAQ entry and refresh the visible list.
   */
  async function handleApproveFaq(entry: AdminAiFaqEntry): Promise<void> {
    const entryId = numericId(entry.id);
    if (!entryId) return;

    setPromptFaqState((currentState) => ({ ...currentState, isSaving: true }));
    try {
      await approveFaqEntry(entryId);
      setPromptFaqState((currentState) => ({
        ...currentState,
        statusMessage: "FAQ freigegeben und für den Index vorgemerkt."
      }));
      await refreshPromptFaq();
    } catch (error) {
      setPromptFaqState((currentState) => ({
        ...currentState,
        errorMessage: failedPromptFaqState(error).errorMessage
      }));
    } finally {
      setPromptFaqState((currentState) => ({ ...currentState, isSaving: false }));
    }
  }

  return {
    handleApproveFaq,
    handleFaqSubmit,
    handlePromptVersionSubmit,
    promptFaqState
  };
}
