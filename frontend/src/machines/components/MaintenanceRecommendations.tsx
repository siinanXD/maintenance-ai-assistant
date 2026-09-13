import type { ReactNode } from "react";

import type { MachineRecommendation } from "../machineTypes";

type MaintenanceRecommendationsProps = {
  readonly recommendations: readonly MachineRecommendation[];
  readonly onHistory: (machineId: number) => Promise<void>;
};

/**
 * Return a German recommendation risk label.
 */
function recommendationRiskLabel(riskLevel: string | undefined): string {
  const labels: Record<string, string> = {
    critical: "kritisch",
    high: "hoch",
    medium: "mittel",
    low: "niedrig"
  };
  return labels[riskLevel || ""] || riskLevel || "niedrig";
}

/**
 * Render preventive maintenance recommendations.
 */
export function MaintenanceRecommendations({
  recommendations,
  onHistory
}: MaintenanceRecommendationsProps): ReactNode {
  return (
    <article className="card app-card lg:order-2 lg:col-span-12">
      <div className="card-body">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Präventive Wartung</h2>
            <p className="panel-meta">
              {recommendations.length
                ? `${recommendations.length} präventive Hinweise aus Aufgaben, Fehlern und Quellen.`
                : "Keine auffälligen Wartungssignale gefunden."}
            </p>
          </div>
          <span className="badge badge-ai">Assist</span>
        </div>
        <div className="resource-card-grid maintenance-recommendation-grid">
          {recommendations.length ? (
            recommendations.map((item) => (
              <article className="resource-card maintenance-recommendation-card" key={`${item.machine?.id || "machine"}-${item.score || 0}`}>
                <div className="resource-card-header">
                  <div>
                    <h3 className="resource-card-title">{item.machine?.name || "Maschine"}</h3>
                    <p className="resource-card-subtitle">{item.reason || "Historie und Quellen prüfen."}</p>
                  </div>
                  <div className="resource-card-badges">
                    <span className="badge badge-ai">{recommendationRiskLabel(item.risk_level)}</span>
                  </div>
                </div>
                <div className="resource-meta-grid">
                  {[
                    ["Score", String(item.score || 0)],
                    ["Aufgaben", String(item.source_counts?.tasks || 0)],
                    ["Fehler", String(item.source_counts?.errors || 0)],
                    ["Quellen", String(item.source_counts?.rag_sources || 0)]
                  ].map(([label, value]) => (
                    <div className="resource-metric" key={label}>
                      <span className="resource-label">{label}</span>
                      <span className="resource-value">{value}</span>
                    </div>
                  ))}
                </div>
                <p className="resource-note">{item.recommended_action || "Nächsten Wartungsschritt planen."}</p>
                <div className="resource-actions">
                  {item.machine?.id ? (
                    <button className="btn btn-outline btn-sm" onClick={() => onHistory(item.machine?.id || 0)} type="button">
                      Historie
                    </button>
                  ) : null}
                </div>
              </article>
            ))
          ) : (
            <p className="panel-meta">Keine präventiven Empfehlungen vorhanden.</p>
          )}
        </div>
      </div>
    </article>
  );
}
