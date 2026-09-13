import type { ReactNode } from "react";

/**
 * Render a collapsible intro for the documents knowledge workflow.
 */
export function DocumentOverviewIntro(): ReactNode {
  return (
    <details className="help-disclosure context-help document-workflow-help" aria-label="So nutzen Sie die Dokumentenübersicht">
      <summary>So nutzen Sie die Dokumentenübersicht</summary>
      <div className="help-disclosure-body">
        <p className="panel-meta">
          Berichte prüfen, Handbücher zuordnen und Freigabe- sowie Indexstatus im KI-Administration
          nachvollziehen, bevor Dokumente als Quelle dienen.
        </p>
      </div>
    </details>
  );
}
