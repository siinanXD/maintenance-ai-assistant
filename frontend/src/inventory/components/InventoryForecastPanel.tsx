import { useState, type FormEvent, type ReactNode } from "react";

import type { ForecastItem, InventoryForecast, UnmatchedForecastTask } from "../inventoryTypes";
import { forecastRiskBadgeClass, inventoryErrorMessage, type MessageState } from "../inventoryUtils";

type InventoryForecastPanelProps = {
  readonly forecast: InventoryForecast | null;
  readonly onForecast: (threshold: number) => Promise<void>;
  readonly threshold: number;
  readonly onThresholdChange: (threshold: number) => void;
};

/**
 * Render one forecast row.
 */
function ForecastRow({ item }: { readonly item: ForecastItem }): ReactNode {
  return (
    <tr>
      <td>{item.material?.name || "-"}</td>
      <td>{item.machine?.name || "-"}</td>
      <td>{String(item.quantity ?? "-")}</td>
      <td><span className={forecastRiskBadgeClass(item.risk_level)}>{item.risk_level || "-"}</span></td>
      <td>{item.task?.title || "-"}</td>
      <td>{[item.recommended_action, item.match_reason].filter(Boolean).join(" | ") || "-"}</td>
    </tr>
  );
}

/**
 * Render an unmatched forecast task.
 */
function UnmatchedTaskRow({ item }: { readonly item: UnmatchedForecastTask }): ReactNode {
  return (
    <div className="stat-row" title={item.recommended_action || item.reason || ""}>
      <span>{item.task.title}</span>
      <strong>{item.risk_level}</strong>
    </div>
  );
}

/**
 * Render the inventory forecast panel.
 */
export function InventoryForecastPanel({
  forecast,
  onForecast,
  threshold,
  onThresholdChange
}: InventoryForecastPanelProps): ReactNode {
  const [message, setMessage] = useState<MessageState>({ text: "", error: false });
  const [busy, setBusy] = useState(false);
  const items = forecast?.items || [];
  const unmatchedTasks = forecast?.unmatched_tasks || [];

  /**
   * Submit the forecast request.
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setMessage({ text: "Prognose wird berechnet...", error: false });

    try {
      await onForecast(threshold);
      setMessage({ text: "", error: false });
    } catch (error) {
      setMessage({ text: inventoryErrorMessage(error), error: true });
    } finally {
      setBusy(false);
    }
  }

  const summary = forecast?.summary || {};
  const summaryText = forecast
    ? [
      `Kritisch: ${summary.critical || 0}`,
      `Hoch: ${summary.high || 0}`,
      `Mittel: ${summary.medium || 0}`,
      unmatchedTasks.length ? `Ohne Maschine: ${unmatchedTasks.length}` : ""
    ].filter(Boolean).join(" | ")
    : message.text;

  return (
    <article className="card app-card lg:order-2 lg:col-span-12">
      <div className="card-body">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Ersatzteil-Prognose</h2>
            <p className="panel-meta">Riskante Aufgaben mit Lagerbestand und Maschinenbezug abgleichen.</p>
          </div>
        </div>
        <form className="toolbar form-actions" id="inventory-forecast-command-form" onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="react-forecast-threshold">Mindestbestand</label>
            <input className="input input-bordered" id="react-forecast-threshold" min="0" name="low_stock_threshold" onChange={(event) => onThresholdChange(Number(event.target.value || 0))} type="number" value={threshold} />
          </div>
          <button className="btn btn-primary" disabled={busy} type="submit">
            {busy ? "Berechnet..." : "Prognose berechnen"}
          </button>
          <span className={`panel-meta${message.error ? " is-error" : ""}`}>
            {summaryText}
          </span>
        </form>
        <div className="table-wrap">
          <table className="table data-table">
            <caption>Ersatzteil-Prognose nach Material, Maschine, Risiko und Empfehlung</caption>
            <thead>
              <tr>
                <th scope="col">Material</th>
                <th scope="col">Maschine</th>
                <th scope="col">Anzahl</th>
                <th scope="col">Risiko</th>
                <th scope="col">Aufgabe</th>
                <th scope="col">Empfehlung</th>
              </tr>
            </thead>
            <tbody>
              {items.length ? (
                items.map((item, index) => <ForecastRow item={item} key={`${item.material?.name || "material"}-${index}`} />)
              ) : (
                <tr>
                  <td colSpan={6}>{forecast ? "Keine kritischen Lagerhinweise gefunden." : "Noch keine Prognose berechnet."}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="forecast-unmatched-list">
          {unmatchedTasks.length ? (
            <>
              <h3 className="panel-title">Aufgaben ohne Maschinenbezug</h3>
              {unmatchedTasks.map((item, index) => <UnmatchedTaskRow item={item} key={`${item.task.title || "task"}-${index}`} />)}
            </>
          ) : null}
        </div>
      </div>
    </article>
  );
}
