import { type Dispatch, type SetStateAction } from "react";

import {
  deleteKnowledgeDocument,
  deleteTrainingEntry,
  queueKnowledgeReindexJob,
  reindexKnowledgeDocument,
  runKnowledgeReindex,
  runRetrievalEvaluation,
  updateKnowledgeQualityStatus,
  type AdminAiPayload
} from "../adminAiApi";
import { type AdminAiFaqEntry } from "../adminAiPromptFaqModel";
import {
  trainingFormFromEntry,
  type AdminAiRagBoardFilters,
  type AdminAiRagBoardState,
  type AdminAiTrainingForm
} from "../adminAiRagBoardModel";
import {
  EMPTY_ADMIN_AI_SOURCE_CHECK_STATE,
  type AdminAiSourceCheckState
} from "../adminAiSourceCheckModel";
import { type AdminAiTechnicalFilters } from "../adminAiTechnicalModel";

type RunAdminAiPayloadAction = (
  statusMessage: string,
  action: () => Promise<AdminAiPayload>
) => Promise<void>;

type AdminAiActionsConfig = {
  readonly handleApproveFaq: (entry: AdminAiFaqEntry) => Promise<void>;
  readonly handleCreateSourceFaq: () => Promise<void>;
  readonly handleFaqSubmit: (form: HTMLFormElement) => Promise<void>;
  readonly handleKnowledgeUpload: (form: HTMLFormElement) => Promise<void>;
  readonly handlePromptVersionSubmit: (form: HTMLFormElement) => Promise<void>;
  readonly handleSaveTraining: (form: AdminAiTrainingForm) => Promise<void>;
  readonly handleSourceFeedback: (rating: string, comment?: string) => Promise<void>;
  readonly handleSourceTestSubmit: (form: HTMLFormElement, intent?: string) => Promise<void>;
  readonly refreshTechnical: () => Promise<void>;
  readonly runRagBoardAction: RunAdminAiPayloadAction;
  readonly runTechnicalAction: RunAdminAiPayloadAction;
  readonly setOverviewChatQuery: Dispatch<SetStateAction<string>>;
  readonly setOverviewEventError: Dispatch<SetStateAction<string>>;
  readonly setRagBoardState: Dispatch<SetStateAction<AdminAiRagBoardState>>;
  readonly setSourceCheckState: Dispatch<SetStateAction<AdminAiSourceCheckState>>;
  readonly updateRagBoardFilter: (key: keyof AdminAiRagBoardFilters, value: string) => void;
  readonly updateTechnicalFilter: (key: keyof AdminAiTechnicalFilters, value: string) => void;
};

/**
 * Return Admin-AI action callbacks separately from data-loading effects.
 */
export function useAdminAiActions(config: AdminAiActionsConfig) {
  return {
    onApproveFaq: (entry: AdminAiFaqEntry) => {
      void config.handleApproveFaq(entry);
    },
    onCreateSourceFaq: () => {
      void config.handleCreateSourceFaq();
    },
    onDeleteKnowledge: (documentId: number) => {
      void config.runRagBoardAction("Dokument wird gelöscht...", () => deleteKnowledgeDocument(documentId));
    },
    onDeleteTraining: (entryId: number) => {
      void config.runRagBoardAction("Training wird gelöscht...", () => deleteTrainingEntry(entryId));
    },
    onFaqSubmit: (form: HTMLFormElement) => {
      void config.handleFaqSubmit(form);
    },
    onKnowledgeFilterChange: config.updateRagBoardFilter,
    onKnowledgeUpload: (form: HTMLFormElement) => {
      void config.handleKnowledgeUpload(form);
    },
    onNetworkFilterChange: config.updateRagBoardFilter,
    onOverviewChatQueryChange: config.setOverviewChatQuery,
    onOverviewEventErrorChange: config.setOverviewEventError,
    onPromptVersionSubmit: (form: HTMLFormElement) => {
      void config.handlePromptVersionSubmit(form);
    },
    onQueueDocument: (documentId: number) => {
      void config.runRagBoardAction("Dokument-Reindex-Job wird eingeplant...", () =>
        queueKnowledgeReindexJob({ document_id: documentId })
      );
    },
    onQueueStale: () => {
      void config.runRagBoardAction("Stale-Reindex-Job wird eingeplant...", () =>
        queueKnowledgeReindexJob({ mode: "stale" })
      );
    },
    onReindexAll: () => {
      void config.runRagBoardAction("Wissen wird neu indexiert...", () => runKnowledgeReindex());
    },
    onReindexDocument: (documentId: number) => {
      void config.runRagBoardAction("Dokument wird neu indexiert...", () =>
        reindexKnowledgeDocument(documentId)
      );
    },
    onReindexStale: () => {
      void config.runRagBoardAction("Veraltete Quellen werden neu indexiert...", () =>
        runKnowledgeReindex("?mode=stale")
      );
    },
    onSaveTraining: (form: AdminAiTrainingForm) => {
      void config.handleSaveTraining(form);
    },
    onSelectTraining: (entry: AdminAiPayload) => {
      config.setRagBoardState((currentState) => ({
        ...currentState,
        trainingForm: trainingFormFromEntry(entry)
      }));
    },
    onSourceFeedback: (rating: string, comment?: string) => {
      void config.handleSourceFeedback(rating, comment);
    },
    onSourceReset: () => {
      config.setSourceCheckState(EMPTY_ADMIN_AI_SOURCE_CHECK_STATE);
    },
    onSourceTestSubmit: (form: HTMLFormElement, intent?: string) => {
      void config.handleSourceTestSubmit(form, intent);
    },
    onTrainingFilterChange: config.updateRagBoardFilter,
    onTrainingFormChange: (form: AdminAiTrainingForm) => {
      config.setRagBoardState((currentState) => ({ ...currentState, trainingForm: form }));
    },
    onTechnicalFilterChange: config.updateTechnicalFilter,
    onTechnicalRefresh: () => {
      void config.refreshTechnical();
    },
    onTechnicalRunEvaluation: () => {
      void config.runTechnicalAction("Golden Eval wird ausgeführt...", runRetrievalEvaluation);
    },
    onUpdateKnowledgeQuality: (documentId: number, qualityStatus: string) => {
      void config.runRagBoardAction("Qualitätsstatus wird gesetzt...", () =>
        updateKnowledgeQualityStatus(documentId, qualityStatus)
      );
    }
  };
}
