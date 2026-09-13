import { type ReactNode } from "react";
import type { AdminAiOverviewLoadState } from "../adminAiOverviewModel";
import { displayText, numberText } from "../adminAiFormat";

/**
 * Render a compact recent-chat panel for the overview.
 */
export function AdminAiOverviewActivity({
  overviewState
}: {
  readonly overviewState: AdminAiOverviewLoadState;
}): ReactNode {
  const recentChats = overviewState.chats.slice(0, 6);

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h3>Letzte AI-Anfragen</h3>
          <p className="panel-meta">Kurzübersicht der jüngsten Chat-Nutzung ohne Antworttext.</p>
        </div>
        <div className="admin-ai-overview-actions">
          <input
            className="input input-bordered input-sm"
            placeholder="Chat-Verlauf filtern"
            type="search"
          />
          <a className="btn btn-ghost btn-sm" href="/admin/ai/source-check">
            Testfrage prüfen
          </a>
        </div>
      </div>
      <div className="stack">
        {recentChats.length ? recentChats.map((chat) => (
          <article className="list-card" key={displayText(chat.id)}>
            <strong>{displayText(chat.created_at, `Chat ${displayText(chat.id)}`)}</strong>
            <small>
              {[
                `Workflow ${displayText(chat.workflow)}`,
                `Quellen ${numberText(chat.source_count)}`,
                `Typ ${displayText(chat.response_type)}`
              ].join(" / ")}
            </small>
          </article>
        )) : (
          <p className="empty-state">Keine jüngsten AI-Anfragen geladen.</p>
        )}
      </div>
    </section>
  );
}
