import { useState, type ReactNode } from "react";

import { ActionDrawer } from "../../components/ui/ActionDrawer";
import { PageActionBar } from "../../components/ui/PageActionBar";
import { createActionDefinition } from "../../components/ui/createActionSchema";
import {
  promptFaqText,
  type AdminAiFaqEntry,
  type AdminAiPromptFaqState
} from "../adminAiPromptFaqModel";
import { FaqRows, PromptList, SnippetList, submitForm, SuggestionList } from "./AdminAiPromptFaqShared";

type AdminAiPromptFaqProps = {
  readonly onApproveFaq: (entry: AdminAiFaqEntry) => void;
  readonly onFaqSubmit: (form: HTMLFormElement) => void;
  readonly onPromptVersionSubmit: (form: HTMLFormElement) => void;
  readonly promptFaqState: AdminAiPromptFaqState;
};

/**
 * Render Prompt and FAQ administration hooks with React-owned data and actions.
 */
export function AdminAiPromptFaq({
  onApproveFaq,
  onFaqSubmit,
  onPromptVersionSubmit,
  promptFaqState
}: AdminAiPromptFaqProps): ReactNode {
  const [activeDrawer, setActiveDrawer] = useState<"faq" | "prompt" | null>(null);

  return (
    <>
      <section className="ai-admin-area" id="ai-prompts">
        <div className="ai-admin-area-header">
          <div>
            <span className="section-kicker">3. Prompt & FAQ</span>
            <h3>AI-Calls und Prompt-Versionen steuern</h3>
            <p className="panel-meta">
              Master-Admins sehen aktive Prompts, Entwürfe und Rollback-Optionen pro Workflow.
            </p>
          </div>
          <span className={`badge badge-ai ${promptFaqState.prompts.length ? "is-active" : "is-stale"}`}>
            {promptFaqState.isLoading ? "Prompts werden geladen" : `${promptFaqState.prompts.length} Prompt-Workflows`}
          </span>
        </div>
        <div className="content-grid two-columns">
          <section className="panel">
            <div className="panel-header">
              <h3>Workflows</h3>
              <span className="panel-meta">Aktive Version, Antwortmodus und Zweck</span>
            </div>
            <PromptList prompts={promptFaqState.prompts} />
          </section>
          <section className="panel">
            <div className="panel-header">
              <h3>Neuer Prompt-Entwurf</h3>
              <span className="panel-meta">Entwurf speichern, danach gezielt aktivieren</span>
            </div>
            <PageActionBar
              label="Prompt Entwurf Aktionen"
              actions={[
                {
                  disabled: promptFaqState.isSaving,
                  onClick: () => setActiveDrawer("prompt"),
                  schema: createActionDefinition("adminPromptDraft"),
                  variant: "primary"
                }
              ]}
            />
            <span className="panel-meta">
              {promptFaqState.promptFormStatus}
            </span>
          </section>
        </div>
        </section>

      <section className="ai-admin-area" id="ai-faq">
        <div className="ai-admin-area-header">
          <div>
            <span className="section-kicker">2. FAQ & Antworten</span>
            <h3>Häufige Fragen in freigegebenes Wissen verwandeln</h3>
            <p className="panel-meta">
              Vorschläge kommen aus Chatverlauf, Wissenslücken und Feedback. Erst freigegebene FAQ
              werden RAG-aktiv.
            </p>
          </div>
          <span className={`badge badge-ai ${promptFaqState.faqEntries.length ? "is-active" : "is-stale"}`}>
            {promptFaqState.isLoading ? "FAQ wird geladen" : `${promptFaqState.faqEntries.length} FAQ-Einträge`}
          </span>
        </div>
        <div className="content-grid two-columns">
          <section className="panel">
            <div className="panel-header">
              <h3>Vorschläge</h3>
              <span className="panel-meta">Top-Fragen, Gaps und negative Signale</span>
            </div>
            <div className="content-grid two-columns">
              <SuggestionList
                emptyText="Noch keine häufigen Fragen."
                heading="Häufige Fragen"
                items={promptFaqState.frequentQuestions}
              />
              <SuggestionList
                emptyText="Noch keine offenen Wissenslücken."
                heading="Offene Wissenslücken"
                items={promptFaqState.knowledgeGaps}
              />
            </div>
          </section>
          <section className="panel">
            <div className="panel-header">
              <h3>FAQ erfassen</h3>
              <span className="panel-meta">Standard ist Entwurf</span>
            </div>
            <PageActionBar
              label="FAQ Entwurf Aktionen"
              actions={[
                {
                  disabled: promptFaqState.isSaving,
                  onClick: () => setActiveDrawer("faq"),
                  schema: createActionDefinition("adminFaqDraft"),
                  variant: "primary"
                }
              ]}
            />
          </section>
        </div>
        <section className="panel mt-4">
          <div className="panel-header">
            <h3>FAQ-Einträge</h3>
            <span className="panel-meta">Freigabe macht den Eintrag indexierbar</span>
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <caption>FAQ-Einträge mit Status und Freigabe</caption>
              <thead>
                <tr>
                  <th scope="col">Frage</th>
                  <th scope="col">Kategorie</th>
                  <th scope="col">Status</th>
                  <th scope="col">Quelle</th>
                  <th scope="col">Aktionen</th>
                </tr>
              </thead>
              <FaqRows entries={promptFaqState.faqEntries} isSaving={promptFaqState.isSaving} onApproveFaq={onApproveFaq} />
            </table>
          </div>
        </section>
        <section className="panel mt-4">
          <div className="panel-header">
            <h3>Antwortbausteine</h3>
            <span className="panel-meta">Fallbacks, Sicherheitswarnungen und Eskalationen</span>
          </div>
          <SnippetList snippets={promptFaqState.responseSnippets} />
        </section>
      </section>
      <ActionDrawer
        definition={createActionDefinition("adminPromptDraft")}
        isOpen={activeDrawer === "prompt"}
        onClose={() => setActiveDrawer(null)}
      >
        <PromptDraftForm
          isSaving={promptFaqState.isSaving}
          onSubmit={onPromptVersionSubmit}
          prompts={promptFaqState.prompts}
          status={promptFaqState.promptFormStatus}
        />
        </ActionDrawer>
      <ActionDrawer
        definition={createActionDefinition("adminFaqDraft")}
        isOpen={activeDrawer === "faq"}
        onClose={() => setActiveDrawer(null)}
      >
        <FaqDraftForm isSaving={promptFaqState.isSaving} onSubmit={onFaqSubmit} />
      </ActionDrawer>
    </>
  );
}

/**
 * Render the admin prompt draft form inside the shared action drawer.
 */
function PromptDraftForm({
  isSaving,
  onSubmit,
  prompts,
  status
}: {
  readonly isSaving: boolean;
  readonly onSubmit: (form: HTMLFormElement) => void;
  readonly prompts: AdminAiPromptFaqState["prompts"];
  readonly status: string;
}): ReactNode {
  return (
    <form className="stack" onSubmit={submitForm(onSubmit)}>
      <select
        className="input input-bordered"
        name="template_id"
        aria-label="Workflow auswählen"
      >
        {prompts.map((prompt) => (
          <option key={promptFaqText(prompt.id)} value={promptFaqText(prompt.id, "")}>
            {promptFaqText(prompt.name)} ({promptFaqText(prompt.workflow_key)})
          </option>
        ))}
      </select>
      <textarea className="input input-bordered" name="system_prompt" rows={9} placeholder="System-Prompt" />
      <textarea
        className="input input-bordered"
        name="user_prompt_template"
        rows={5}
        placeholder="User-Prompt-Template, z. B. {question}, {context}, {payload_json}"
      />
      <input className="input input-bordered" name="change_note" placeholder="Änderungsnotiz" />
      <div className="toolbar">
        <button className="btn btn-primary" disabled={isSaving} type="submit">
          Entwurf speichern
        </button>
        <span className="panel-meta">
          {status}
        </span>
      </div>
    </form>
  );
}

/**
 * Render the admin FAQ draft form inside the shared action drawer.
 */
function FaqDraftForm({
  isSaving,
  onSubmit
}: {
  readonly isSaving: boolean;
  readonly onSubmit: (form: HTMLFormElement) => void;
}): ReactNode {
  return (
    <form className="stack" onSubmit={submitForm(onSubmit)}>
      <textarea className="input input-bordered" name="question" rows={3} placeholder="Frage" />
      <textarea className="input input-bordered" name="answer" rows={5} placeholder="Freigegebene Antwort" />
      <div className="content-grid two-columns">
        <input className="input input-bordered" name="category" placeholder="Kategorie" />
        <input className="input input-bordered" name="keywords" placeholder="Keywords" />
        <input className="input input-bordered" name="machine" placeholder="Maschine optional" />
        <input className="input input-bordered" name="department" placeholder="Abteilung optional" />
      </div>
      <button className="btn btn-primary" disabled={isSaving} type="submit">
        FAQ-Entwurf speichern
      </button>
    </form>
  );
}
