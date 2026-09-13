import { useMemo, type ReactNode } from "react";

import { useCanUseAdminAi } from "./adminAiAccess";
import { resolveAdminAiView, type AdminAiView } from "./adminAiViews";
import { AdminAiOperateHub } from "./components/AdminAiOperateHub";
import { AdminAiEffectiveness } from "./components/AdminAiEffectiveness";
import { AdminAiPromptFaq } from "./components/AdminAiPromptFaq";
import { AdminAiRagBoard } from "./components/AdminAiRagBoard";
import { AdminAiSourceCheck } from "./components/AdminAiSourceCheck";
import { AdminAiTechnical } from "./components/AdminAiTechnical";
import { AdminAiShell } from "./components/AdminAiShell";
import { useAdminAiData } from "./hooks/useAdminAiData";

type AdminAiData = ReturnType<typeof useAdminAiData>;

/**
 * AI administration: operations, observability, answer checks, prompts and knowledge.
 */
export function AdminAiApp(): ReactNode {
  const view = useMemo(() => resolveAdminAiView(window.location.pathname), []);
  const canUseAdminAi = useCanUseAdminAi();
  const data = useAdminAiData(view, canUseAdminAi);

  return (
    <AdminAiShell
      effectivenessState={data.effectivenessState}
      overviewState={data.overviewState}
      promptFaqState={data.promptFaqState}
      ragBoardState={data.ragBoardState}
      sourceCheckState={data.sourceCheckState}
      technicalState={data.technicalState}
      view={view}
    >
      {canUseAdminAi ? <AdminAiViewContent data={data} view={view} /> : <AdminAiAccessNotice />}
    </AdminAiShell>
  );
}

/**
 * Render the section for the active Admin-AI route.
 */
function AdminAiViewContent({ data, view }: { readonly data: AdminAiData; readonly view: AdminAiView }): ReactNode {
  switch (view) {
    case "rag_board":
      return (
        <AdminAiRagBoard
          onCreateFaq={data.onCreateSourceFaq}
          onDeleteKnowledge={data.onDeleteKnowledge}
          onDeleteTraining={data.onDeleteTraining}
          onFeedback={data.onSourceFeedback}
          onKnowledgeFilterChange={data.onKnowledgeFilterChange}
          onKnowledgeUpload={data.onKnowledgeUpload}
          onNetworkFilterChange={data.onNetworkFilterChange}
          onQueueDocument={data.onQueueDocument}
          onQueueStale={data.onQueueStale}
          onReindexAll={data.onReindexAll}
          onReindexDocument={data.onReindexDocument}
          onReindexStale={data.onReindexStale}
          onReset={data.onSourceReset}
          onSaveTraining={data.onSaveTraining}
          onSelectTraining={data.onSelectTraining}
          onSourceTestSubmit={data.onSourceTestSubmit}
          onTrainingFilterChange={data.onTrainingFilterChange}
          onTrainingFormChange={data.onTrainingFormChange}
          onUpdateKnowledgeQuality={data.onUpdateKnowledgeQuality}
          ragBoardState={data.ragBoardState}
          sourceCheckState={data.sourceCheckState}
        />
      );
    case "source_check":
      return (
        <AdminAiSourceCheck
          onCreateFaq={data.onCreateSourceFaq}
          onFeedback={data.onSourceFeedback}
          onReset={data.onSourceReset}
          onSourceTestSubmit={data.onSourceTestSubmit}
          sourceCheckState={data.sourceCheckState}
        />
      );
    case "prompt_faq":
      return (
        <AdminAiPromptFaq
          onApproveFaq={data.onApproveFaq}
          onFaqSubmit={data.onFaqSubmit}
          onPromptVersionSubmit={data.onPromptVersionSubmit}
          promptFaqState={data.promptFaqState}
        />
      );
    case "effectiveness":
      return <AdminAiEffectiveness effectivenessState={data.effectivenessState} />;
    case "technical":
      return (
        <AdminAiTechnical
          onFilterChange={data.onTechnicalFilterChange}
          onQueueStale={data.onQueueStale}
          onRefresh={data.onTechnicalRefresh}
          onReindexAll={data.onReindexAll}
          onReindexStale={data.onReindexStale}
          onRunEvaluation={data.onTechnicalRunEvaluation}
          technicalState={data.technicalState}
        />
      );
    default:
      return <AdminAiOperateHub overviewState={data.overviewState} />;
  }
}

/**
 * Shown to roles that cannot call the Admin-AI API.
 */
function AdminAiAccessNotice(): ReactNode {
  return (
    <section className="ai-admin-area">
      <section className="panel">
        <div className="panel-header">
          <div>
            <span className="section-kicker">Zugriff</span>
            <h3>KI-Administration ist Master-Admins vorbehalten</h3>
            <p className="panel-meta">Die Admin-AI-API ist im Backend nur für Master-Admins freigegeben.</p>
          </div>
        </div>
      </section>
    </section>
  );
}
