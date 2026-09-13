import type { ReactNode } from "react";

import { formatMoney } from "../../formatters/number";
import type { ReorderSuggestions } from "../inventoryTypes";

type ReorderPanelProps = {
  readonly suggestions: ReorderSuggestions | null;
};

/**
 * Materials at or below minimum stock with the proposed order quantity.
 */
export function ReorderPanel({ suggestions }: ReorderPanelProps): ReactNode {
  const items = suggestions?.items || [];

  return (
    <article className="card app-card lg:col-span-12" data-inventory-reorder>
      <div className="card-body">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Bestellvorschlag</h2>
            <p className="panel-meta">
              Unter Mindestbestand. Menge füllt auf das Doppelte des Minimums auf und deckt den Verbrauch der letzten 90 Tage während der Lieferzeit.
            </p>
          </div>
          {items.length ? <span className="badge badge-priority is-soon">{formatMoney(suggestions?.total_value)}</span> : null}
        </div>
        {suggestions === null ? <p className="panel-meta">Wird berechnet…</p> : null}
        {suggestions && !items.length ? <p className="panel-meta">Alle Positionen liegen über dem Mindestbestand.</p> : null}
        {items.length ? (
          <div className="table-wrap">
            <table className="data-table reorder-table">
              <thead>
                <tr>
                  <th scope="col">Material</th>
                  <th className="is-number" scope="col">Bestand / Min.</th>
                  <th className="is-number" scope="col">Verbrauch 90 T.</th>
                  <th className="is-number" scope="col">Lieferzeit</th>
                  <th className="is-number" scope="col">Bestellen</th>
                  <th className="is-number" scope="col">Wert</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.material.id}>
                    <td>
                      <strong>{item.material.name}</strong>
                      <small>{item.material.manufacturer || "Hersteller offen"}</small>
                    </td>
                    <td className="is-number">{item.material.quantity} / {item.material.min_quantity}</td>
                    <td className="is-number">{item.used_last_90_days}</td>
                    <td className="is-number">{item.material.lead_time_days ? `${item.material.lead_time_days} T.` : "–"}</td>
                    <td className="is-number"><strong>{item.order_quantity}</strong></td>
                    <td className="is-number">{formatMoney(item.order_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </article>
  );
}
