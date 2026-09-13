import { type FormEvent, type ReactNode } from "react";

import {
  activePromptVersion,
  promptFaqText,
  statusTone,
  suggestionCountText,
  type AdminAiFaqEntry,
  type AdminAiFaqSuggestion,
  type AdminAiPromptTemplate,
  type AdminAiResponseSnippet
} from "../adminAiPromptFaqModel";

/**
 * Wrap a form submit callback with default browser-submit prevention.
 */
export function submitForm(handler: (form: HTMLFormElement) => void) {
  return (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    handler(event.currentTarget);
  };
}

/**
 * Render prompt workflow cards.
 */
export function PromptList({ prompts }: { readonly prompts: readonly AdminAiPromptTemplate[] }): ReactNode {
  return (
    <div className="stack">
      {prompts.length ? (
        prompts.map((prompt) => {
          const activeVersion = activePromptVersion(prompt);
          return (
            <article className="training-card" key={promptFaqText(prompt.id)}>
              <strong>{promptFaqText(prompt.name)} ({promptFaqText(prompt.workflow_key)})</strong>
              <small>{promptFaqText(prompt.purpose, "Prompt-Workflow")}</small>
              <div className="training-card-meta">
                <span className="status-pill is-active">{promptFaqText(prompt.response_mode)}</span>
                <span className={`status-pill ${activeVersion ? "is-active" : "is-stale"}`}>
                  {activeVersion ? `v${promptFaqText(activeVersion.version)} aktiv` : "kein aktiver Prompt"}
                </span>
              </div>
            </article>
          );
        })
      ) : (
        <div className="admin-empty">
          <strong>Keine Prompt-Workflows geladen.</strong>
          <span>Nach dem Laden erscheinen hier aktive Prompt-Versionen.</span>
        </div>
      )}
    </div>
  );
}

/**
 * Render one FAQ suggestion list.
 */
export function SuggestionList({
  emptyText,
  heading,
  items
}: {
  readonly emptyText: string;
  readonly heading: string;
  readonly items: readonly AdminAiFaqSuggestion[];
}): ReactNode {
  return (
    <div className="stats-list">
      <div className="stat-row"><span>{heading}</span><strong>{items.length}</strong></div>
      {items.length ? (
        items.slice(0, 8).map((item) => (
          <div className="stat-row" key={`${promptFaqText(item.question)}:${suggestionCountText(item)}`}>
            <span>{promptFaqText(item.question)}</span>
            <strong>{suggestionCountText(item)}</strong>
          </div>
        ))
      ) : (
        <div className="stat-row"><span>{heading}</span><strong>{emptyText}</strong></div>
      )}
    </div>
  );
}

/**
 * Render FAQ table rows.
 */
export function FaqRows({
  entries,
  isSaving,
  onApproveFaq
}: {
  readonly entries: readonly AdminAiFaqEntry[];
  readonly isSaving: boolean;
  readonly onApproveFaq: (entry: AdminAiFaqEntry) => void;
}): ReactNode {
  return (
    <tbody>
      {entries.length ? (
        entries.map((entry) => (
          <tr key={promptFaqText(entry.id)}>
            <td>{promptFaqText(entry.question)}</td>
            <td>{promptFaqText(entry.category)}</td>
            <td><span className={`status-pill ${statusTone(entry.status)}`}>{promptFaqText(entry.status)}</span></td>
            <td>{promptFaqText(entry.source)}</td>
            <td>
              {entry.status !== "approved" ? (
                <button className="btn btn-secondary btn-sm" disabled={isSaving} onClick={() => onApproveFaq(entry)} type="button">
                  Freigeben
                </button>
              ) : null}
            </td>
          </tr>
        ))
      ) : (
        <tr>
          <td colSpan={5}>
            <div className="admin-empty">
              <strong>Noch keine FAQ-Einträge.</strong>
              <span>Lege einen Entwurf an oder nutze Vorschläge.</span>
            </div>
          </td>
        </tr>
      )}
    </tbody>
  );
}

/**
 * Render reusable response snippets.
 */
export function SnippetList({ snippets }: { readonly snippets: readonly AdminAiResponseSnippet[] }): ReactNode {
  return (
    <div className="stack">
      {snippets.length ? (
        snippets.map((snippet) => (
          <div className="stat-row" key={`${promptFaqText(snippet.category)}:${promptFaqText(snippet.title)}`}>
            <span>{promptFaqText(snippet.title)}</span>
            <strong>{promptFaqText(snippet.category)} / {snippet.is_active ? "aktiv" : "inaktiv"}</strong>
          </div>
        ))
      ) : (
        <div className="stat-row"><span>Keine Antwortbausteine</span><strong>Noch nicht gepflegt</strong></div>
      )}
    </div>
  );
}
