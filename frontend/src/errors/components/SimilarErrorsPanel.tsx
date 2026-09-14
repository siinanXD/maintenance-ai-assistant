import type { ReactNode } from "react";

import type { SimilarErrorResult } from "../errorTypes";

type SimilarErrorsPanelProps = {
  readonly result: SimilarErrorResult | null;
};

/**
 * Render catalog entries similar to the current description.
 */
export function SimilarErrorsPanel({ result }: SimilarErrorsPanelProps): ReactNode {
  const matches = result?.results || [];

  if (!result) {
    return null;
  }

  return (
    <details className="help-disclosure ui-secondary-panel incident-similar-disclosure" open>
      <summary>
        Ähnliche Fehler
        {matches.length ? ` (${matches.length})` : ""}
      </summary>
      <div className="help-disclosure-body">
        <p className="panel-meta">Bestehende Katalogeinträge vor dem Speichern prüfen.</p>
        <div className="table-wrap bounded-table-wrap">
        <table className="table data-table">
          <caption>Ähnliche vorhandene Fehler vor dem Speichern</caption>
          <thead>
            <tr>
              <th scope="col">Score</th>
              <th scope="col">Code</th>
              <th scope="col">Maschine</th>
              <th scope="col">Fehler</th>
              <th scope="col">Grund</th>
            </tr>
          </thead>
          <tbody>
            {matches.length ? matches.map((match) => (
              <tr key={`${match.entry.id}-${match.score}`}>
                <td>{match.score}</td>
                <td><span className="badge status-badge is-open">{match.entry.error_code || "CODE"}</span></td>
                <td>{match.entry.machine || "-"}</td>
                <td>{match.entry.title || "-"}</td>
                <td>{match.reason || "-"}</td>
              </tr>
            )) : (
              <tr>
                <td colSpan={5}>
                  <div className="guided-empty-state">
                    <strong>Keine ähnlichen Fehler gefunden</strong>
                    <p>Lege den Eintrag an, wenn Code, Maschine und Ursache plausibel sind. Er wird danach als Quelle für spätere Analysen nutzbar.</p>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
      </div>
    </details>
  );
}
