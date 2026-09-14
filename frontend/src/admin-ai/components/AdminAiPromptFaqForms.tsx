import { type ReactNode } from "react";
import { promptFaqText, type AdminAiPromptFaqState } from "../adminAiPromptFaqModel";
import { submitForm } from "./AdminAiPromptFaqShared";

/**
 * Render the admin prompt draft form inside the shared action drawer.
 */
export function PromptDraftForm({
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
export function FaqDraftForm({
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
