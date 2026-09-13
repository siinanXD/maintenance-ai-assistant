import { type ReactNode } from "react";

import { AdminAiEffectiveness } from "./AdminAiSectionsEffectiveness";
import { AdminAiOverview } from "./AdminAiSectionsOverview";
import { AdminAiPromptFaq } from "./AdminAiSectionsPromptFaq";
import { AdminAiRagBoard } from "./AdminAiSectionsRagBoard";
import { AdminAiSourceCheck } from "./AdminAiSectionsSourceCheck";
import { AdminAiTechnical } from "./AdminAiSectionsTechnical";
import { AdminAiShell } from "./AdminAiShell";
import { type AdminAiView } from "./AdminAiTypes";
import { type AdminAiEffectivenessState } from "./adminAiEffectivenessModel";
import { type AdminAiOverviewLoadState } from "./adminAiOverviewModel";
import { type AdminAiFaqEntry, type AdminAiPromptFaqState } from "./adminAiPromptFaqModel";
import { type AdminAiRagBoardState, type AdminAiTrainingForm } from "./adminAiRagBoardModel";
import { useAdminAiRoleAccess } from "./adminAiRoleAccess";
import { type AdminAiSourceCheckState } from "./adminAiSourceCheckModel";
import { type AdminAiTechnicalFilters, type AdminAiTechnicalState } from "./adminAiTechnicalModel";

export type AdminAiMarkupProps = {
  readonly effectivenessState: AdminAiEffectivenessState;
  readonly onDeleteKnowledge: (documentId: number) => void;
  readonly onDeleteTraining: (entryId: number) => void;
  readonly onApproveFaq: (entry: AdminAiFaqEntry) => void;
  readonly onCreateSourceFaq: () => void;
  readonly onFaqSubmit: (form: HTMLFormElement) => void;
  readonly onKnowledgeFilterChange: (key: keyof AdminAiRagBoardState["filters"], value: string) => void;
  readonly onKnowledgeUpload: (form: HTMLFormElement) => void;
  readonly onNetworkFilterChange: (key: keyof AdminAiRagBoardState["filters"], value: string) => void;
  readonly onOverviewChatQueryChange: (value: string) => void;
  readonly onOverviewEventErrorChange: (value: string) => void;
  readonly onPromptVersionSubmit: (form: HTMLFormElement) => void;
  readonly onQueueDocument: (documentId: number) => void;
  readonly onQueueStale: () => void;
  readonly onReindexAll: () => void;
  readonly onReindexDocument: (documentId: number) => void;
  readonly onReindexStale: () => void;
  readonly onSaveTraining: (form: AdminAiTrainingForm) => void;
  readonly onSelectTraining: (entry: Record<string, unknown>) => void;
  readonly onSourceFeedback: (rating: string, comment?: string) => void;
  readonly onSourceReset: () => void;
  readonly onSourceTestSubmit: (form: HTMLFormElement, intent?: string) => void;
  readonly onTrainingFilterChange: (key: keyof AdminAiRagBoardState["filters"], value: string) => void;
  readonly onTrainingFormChange: (form: AdminAiTrainingForm) => void;
  readonly onTechnicalFilterChange: (key: keyof AdminAiTechnicalFilters, value: string) => void;
  readonly onTechnicalRefresh: () => void;
  readonly onTechnicalRunEvaluation: () => void;
  readonly onUpdateKnowledgeQuality: (documentId: number, qualityStatus: string) => void;
  readonly overviewState: AdminAiOverviewLoadState;
  readonly overviewChatQuery: string;
  readonly overviewEventError: string;
  readonly promptFaqState: AdminAiPromptFaqState;
  readonly ragBoardState: AdminAiRagBoardState;
  readonly sourceCheckState: AdminAiSourceCheckState;
  readonly technicalState: AdminAiTechnicalState;
  readonly view: AdminAiView;
};

/**
 * Render the canonical Admin-AI view markup with legacy runtime hooks intact.
 */
export function AdminAiMarkup({
  effectivenessState,
  onDeleteKnowledge,
  onDeleteTraining,
  onApproveFaq,
  onCreateSourceFaq,
  onFaqSubmit,
  onKnowledgeFilterChange,
  onKnowledgeUpload,
  onNetworkFilterChange,
  onPromptVersionSubmit,
  onQueueDocument,
  onQueueStale,
  onReindexAll,
  onReindexDocument,
  onReindexStale,
  onSaveTraining,
  onSelectTraining,
  onSourceFeedback,
  onSourceReset,
  onSourceTestSubmit,
  onTrainingFilterChange,
  onTrainingFormChange,
  onTechnicalFilterChange,
  onTechnicalRefresh,
  onTechnicalRunEvaluation,
  onUpdateKnowledgeQuality,
  overviewState,
  promptFaqState,
  ragBoardState,
  sourceCheckState,
  technicalState,
  view
}: AdminAiMarkupProps): ReactNode {
  const roleAccess = useAdminAiRoleAccess();

  return (
    <AdminAiShell
      effectivenessState={effectivenessState}
      overviewState={overviewState}
      promptFaqState={promptFaqState}
      ragBoardState={ragBoardState}
      sourceCheckState={sourceCheckState}
      technicalState={technicalState}
      view={view}
    >
      {adminAiViewContent({
        effectivenessState,
        onDeleteKnowledge,
        onDeleteTraining,
        onApproveFaq,
        onCreateSourceFaq,
        onFaqSubmit,
        onKnowledgeFilterChange,
        onKnowledgeUpload,
        onNetworkFilterChange,
        onPromptVersionSubmit,
        onQueueDocument,
        onQueueStale,
        onReindexAll,
        onReindexDocument,
        onReindexStale,
        onSaveTraining,
        onSelectTraining,
        onSourceFeedback,
        onSourceReset,
        onSourceTestSubmit,
        onTrainingFilterChange,
        onTrainingFormChange,
        onTechnicalFilterChange,
        onTechnicalRefresh,
        onTechnicalRunEvaluation,
        onUpdateKnowledgeQuality,
        overviewState,
        promptFaqState,
        ragBoardState,
        sourceCheckState,
        technicalState,
        view,
        canUseAdminAiApi: roleAccess.canUseAdminAiApi,
        isTechnicalRole: roleAccess.isTechnicalRole
      })}
    </AdminAiShell>
  );
}

type AdminAiViewContentProps = Omit<
  AdminAiMarkupProps,
  | "onOverviewChatQueryChange"
  | "onOverviewEventErrorChange"
  | "overviewChatQuery"
  | "overviewEventError"
> & {
  readonly canUseAdminAiApi: boolean;
  readonly isTechnicalRole: boolean;
};

/**
 * Render the active Admin-AI section for the current canonical route.
 */
function adminAiViewContent({
  effectivenessState,
  onDeleteKnowledge,
  onDeleteTraining,
  onApproveFaq,
  onCreateSourceFaq,
  onFaqSubmit,
  onKnowledgeFilterChange,
  onKnowledgeUpload,
  onNetworkFilterChange,
  onPromptVersionSubmit,
  onQueueDocument,
  onQueueStale,
  onReindexAll,
  onReindexDocument,
  onReindexStale,
  onSaveTraining,
  onSelectTraining,
  onSourceFeedback,
  onSourceReset,
  onSourceTestSubmit,
  onTrainingFilterChange,
  onTrainingFormChange,
  onTechnicalFilterChange,
  onTechnicalRefresh,
  onTechnicalRunEvaluation,
  onUpdateKnowledgeQuality,
  overviewState,
  promptFaqState,
  ragBoardState,
  sourceCheckState,
  technicalState,
  view,
  canUseAdminAiApi,
  isTechnicalRole
}: AdminAiViewContentProps): ReactNode {
  if (!canUseAdminAiApi) {
    return <AdminAiApiRoleNotice />;
  }

  if (view === "rag_board") {
    return (
      <AdminAiRagBoard
        onCreateFaq={onCreateSourceFaq}
        onDeleteKnowledge={onDeleteKnowledge}
        onDeleteTraining={onDeleteTraining}
        onFeedback={onSourceFeedback}
        onKnowledgeFilterChange={onKnowledgeFilterChange}
        onKnowledgeUpload={onKnowledgeUpload}
        onNetworkFilterChange={onNetworkFilterChange}
        onQueueDocument={onQueueDocument}
        onQueueStale={onQueueStale}
        onReindexAll={onReindexAll}
        onReindexDocument={onReindexDocument}
        onReindexStale={onReindexStale}
        onReset={onSourceReset}
        onSaveTraining={onSaveTraining}
        onSelectTraining={onSelectTraining}
        onSourceTestSubmit={onSourceTestSubmit}
        onTrainingFilterChange={onTrainingFilterChange}
        onTrainingFormChange={onTrainingFormChange}
        onUpdateKnowledgeQuality={onUpdateKnowledgeQuality}
        ragBoardState={ragBoardState}
        sourceCheckState={sourceCheckState}
      />
    );
  }
  if (view === "source_check") {
    return (
      <AdminAiSourceCheck
        onCreateFaq={onCreateSourceFaq}
        onFeedback={onSourceFeedback}
        onReset={onSourceReset}
        onSourceTestSubmit={onSourceTestSubmit}
        sourceCheckState={sourceCheckState}
      />
    );
  }
  if (view === "prompt_faq") {
    return (
      <AdminAiPromptFaq
        onApproveFaq={onApproveFaq}
        onFaqSubmit={onFaqSubmit}
        onPromptVersionSubmit={onPromptVersionSubmit}
        promptFaqState={promptFaqState}
      />
    );
  }
  if (view === "effectiveness") {
    return <AdminAiEffectiveness effectivenessState={effectivenessState} />;
  }
  if (view === "technical") {
    if (!isTechnicalRole) {
      return <AdminAiTechnicalRoleNotice />;
    }
    return (
      <AdminAiTechnical
        onFilterChange={onTechnicalFilterChange}
        onQueueStale={onQueueStale}
        onRefresh={onTechnicalRefresh}
        onReindexAll={onReindexAll}
        onReindexStale={onReindexStale}
        onRunEvaluation={onTechnicalRunEvaluation}
        technicalState={technicalState}
      />
    );
  }
  return <AdminAiOverview overviewState={overviewState} />;
}

/**
 * Render the role notice for hidden technical AI diagnostics.
 */
function AdminAiTechnicalRoleNotice(): ReactNode {
  return (
    <section className="ai-admin-area" id="ai-technical" data-ai-admin-area="technical">
      <section className="panel">
        <div className="panel-header">
          <div>
            <span className="section-kicker">Observability</span>
            <h3>Observability ist für Master Admin sichtbar</h3>
            <p className="panel-meta">
              Roh-Prompts, Debug-Panels und interne Retrieval-Diagnosen folgen dem Backend-Vertrag
              der Admin-AI-API und bleiben für andere Rollen ausgeblendet.
            </p>
          </div>
        </div>
      </section>
    </section>
  );
}

/**
 * Render the AI Admin access notice when the stored role cannot call Admin-AI APIs.
 */
function AdminAiApiRoleNotice(): ReactNode {
  return (
    <section className="ai-admin-area" data-ai-admin-area="access-denied">
      <section className="panel">
        <div className="panel-header">
          <div>
            <span className="section-kicker">AI Admin Zugriff</span>
            <h3>AI Admin ist für Master Admin freigegeben</h3>
            <p className="panel-meta">
              Die Admin-AI-API ist im Backend mit Master-Admin-Rechten geschützt. Deshalb blendet
              das Frontend API-abhängige AI-Admin-Bereiche für andere Rollen aus, statt nicht
              nutzbare Panels zu laden.
            </p>
          </div>
        </div>
      </section>
    </section>
  );
}
