import { useAdminAiActions } from "./useAdminAiActions";
import { useAdminAiEffectivenessData } from "./useAdminAiEffectivenessData";
import { useAdminAiOverviewData } from "./useAdminAiOverviewData";
import { useAdminAiPromptFaqData } from "./useAdminAiPromptFaqData";
import { useAdminAiRagBoardData } from "./useAdminAiRagBoardData";
import { useAdminAiSourceCheckData } from "./useAdminAiSourceCheckData";
import { useAdminAiTechnicalData } from "./useAdminAiTechnicalData";
import { type AdminAiView } from "../adminAiViews";

/**
 * Compose Admin-AI data hooks and expose the canonical page props.
 */
export function useAdminAiData(adminAiView: AdminAiView, canUseAdminAiApi: boolean) {
  const overviewData = useAdminAiOverviewData(adminAiView, canUseAdminAiApi);
  const effectivenessData = useAdminAiEffectivenessData(adminAiView, canUseAdminAiApi);
  const promptFaqData = useAdminAiPromptFaqData(adminAiView, canUseAdminAiApi);
  const ragBoardData = useAdminAiRagBoardData(adminAiView, canUseAdminAiApi);
  const sourceCheckData = useAdminAiSourceCheckData();
  const technicalData = useAdminAiTechnicalData(adminAiView, canUseAdminAiApi);

  const actions = useAdminAiActions({
    handleApproveFaq: promptFaqData.handleApproveFaq,
    handleCreateSourceFaq: sourceCheckData.handleCreateSourceFaq,
    handleFaqSubmit: promptFaqData.handleFaqSubmit,
    handleKnowledgeUpload: ragBoardData.handleKnowledgeUpload,
    handlePromptVersionSubmit: promptFaqData.handlePromptVersionSubmit,
    handleSaveTraining: ragBoardData.handleSaveTraining,
    handleSourceFeedback: sourceCheckData.handleSourceFeedback,
    handleSourceTestSubmit: sourceCheckData.handleSourceTestSubmit,
    refreshTechnical: technicalData.refreshTechnical,
    runRagBoardAction: ragBoardData.runRagBoardAction,
    runTechnicalAction: technicalData.runTechnicalAction,
    setOverviewChatQuery: overviewData.setOverviewChatQuery,
    setOverviewEventError: overviewData.setOverviewEventError,
    setRagBoardState: ragBoardData.setRagBoardState,
    setSourceCheckState: sourceCheckData.setSourceCheckState,
    updateRagBoardFilter: ragBoardData.updateRagBoardFilter,
    updateTechnicalFilter: technicalData.updateTechnicalFilter
  });

  return {
    effectivenessState: effectivenessData.effectivenessState,
    overviewChatQuery: overviewData.overviewChatQuery,
    overviewEventError: overviewData.overviewEventError,
    overviewState: overviewData.overviewState,
    promptFaqState: promptFaqData.promptFaqState,
    ragBoardState: ragBoardData.ragBoardState,
    sourceCheckState: sourceCheckData.sourceCheckState,
    technicalState: technicalData.technicalState,
    ...actions
  };
}
