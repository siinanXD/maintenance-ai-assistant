import { useState, type FormEvent, type ReactNode } from "react";

import { askMachineAssistant } from "../machineApi";
import type { MachineAssistantSource, MachineHistory } from "../machineTypes";
import { dateLabel, machineErrorMessage } from "../machineUtils";

type MachineHistoryPanelProps = {
  readonly history: MachineHistory | null;
};

/**
 * Render assistant source rows.
 */
function AssistantSources({ sources }: { readonly sources: readonly MachineAssistantSource[] }): ReactNode {
  if (!sources.length) return null;

  return (
    <div className="rag-source-list">
      {sources.map((source, index) => (
        <article className="rag-source-card" key={`${source.title || "source"}-${index}`}>
          <strong>{source.title || "Quelle"}</strong>
          <span>{source.source_type || source.type || "source"}</span>
        </article>
      ))}
    </div>
  );
}

/**
 * Render machine history and assistant.
 */
export function MachineHistoryPanel({ history }: MachineHistoryPanelProps): ReactNode {
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [question, setQuestion] = useState("");
  const [sources, setSources] = useState<readonly MachineAssistantSource[]>([]);
  const counts = history?.source_counts || {};

  /**
   * Ask the machine assistant for the active history machine.
   */
  async function handleAsk(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!history?.machine?.id) return;
    setBusy(true);
    setAnswer("Maschinen-Assistent denkt...");

    try {
      const result = await askMachineAssistant(history.machine.id, question);
      const fallback = result.diagnostics?.fallback_used || result.diagnostics?.status === "fallback_used"
        ? "Ausweichantwort: "
        : "";
      setAnswer(`${fallback}${result.answer || ""}`);
      setSources(result.sources || []);
    } catch (error) {
      setAnswer(machineErrorMessage(error));
      setSources([]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="card app-card lg:order-3 lg:col-span-12" data-machine-history-panel hidden={!history}>
      <div className="card-body">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">
              {history ? `Anlagenakte: ${history.machine.name}` : "Anlagenakte"}
            </h2>
            <p className="panel-meta">{history?.summary?.text || "Historie einer Maschine aus Aufgaben, Fehlern und Dokumenten."}</p>
          </div>
        </div>
        <div className="stats-list">
          {[
            ["Aufgaben", counts.tasks || 0],
            ["Fehler", counts.errors || 0],
            ["Dokumente", counts.documents || 0],
            ["Gesamt", counts.total || 0]
          ].map(([label, value]) => (
            <div className="stat-row" key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
        <form className="toolbar form-actions" data-machine-assistant-form onSubmit={handleAsk}>
          <div className="field">
            <label htmlFor="react-machine-assistant-question">Maschinenfrage</label>
            <input className="input input-bordered" disabled={busy} id="react-machine-assistant-question" name="question" onChange={(event) => setQuestion(event.target.value)} placeholder="Was sollte ich als nächstes prüfen?" value={question} />
          </div>
          <button className="btn btn-primary" disabled={busy} type="submit">{busy ? "Fragt..." : "Fragen"}</button>
        </form>
        <div className={`ai-response${answer.startsWith("Die ") ? " is-error" : ""}`}>{answer}</div>
        <div className="rag-source-panel" hidden={!sources.length}>
          <AssistantSources sources={sources} />
        </div>
        <div className="timeline-list">
          {history?.timeline?.length ? (
            history.timeline.map((item, index) => (
              <article className="machine-profile-record" key={`${item.title || "item"}-${index}`}>
                <div className="machine-profile-record-header">
                  <div>
                    <h3>{item.title || "-"}</h3>
                    <p>{[item.type, dateLabel(item.date)].filter(Boolean).join(" · ")}</p>
                  </div>
                  <div className="machine-profile-record-badges">
                    <span className="badge badge-status is-open">{item.status || "-"}</span>
                  </div>
                </div>
                <p className="machine-profile-record-summary">{item.summary || ""}</p>
                {item.url ? (
                  <div className="machine-profile-record-actions">
                    <a className="btn btn-outline btn-sm" href={item.url}>Öffnen</a>
                  </div>
                ) : null}
              </article>
            ))
          ) : (
            <div className="empty-state">Keine Historie gefunden.</div>
          )}
        </div>
      </div>
    </article>
  );
}
