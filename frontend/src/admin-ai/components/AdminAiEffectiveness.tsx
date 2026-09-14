import { type ReactNode } from "react";

import {
  capabilityGroups,
  effectivenessKpiValue,
  effectivenessRiskRows,
  helpfulRateText,
  langfuseMetricValue,
  langfuseModelRows,
  langfuseStatus,
  langfuseWorkflowRows,
  priceStatusText,
  safetyFields,
  safetyStatus,
  userCostCell,
  workflowCostRows,
  type AdminAiEffectivenessState
} from "../adminAiEffectivenessModel";
import { capabilityStatus, capabilityTitle, MiniBarList } from "./AdminAiEffectivenessShared";
import { StatsList } from "./AdminAiShared";

const COST_KPIS = [
  ["events_total", "Events"],
  ["total_tokens", "Tokens"],
  ["estimated_cost_usd", "Kosten USD"]
] as const;

const LANGFUSE_KPIS = [
  ["total_cost_usd", "Langfuse Kosten"],
  ["total_tokens", "Langfuse Tokens"],
  ["observation_count", "Observations"],
  ["cost_per_1k_tokens", "Kosten / 1k"]
] as const;

const SAFETY_FIELDS = [
  [
    "fallback_rate",
    "Ausweichbetrieb-Rate",
    "Viele Ausweichbetriebe deuten auf Anbieter-, Quellen- oder Prompt-Probleme hin."
  ],
  ["safety_risk_count", "Sicherheitsrisiken", "Riskante Aussagen müssen fachlich kontrolliert werden."],
  ["no_source_rate", "Antworten ohne Quellen", "Antworten ohne Quellen brauchen Datenpflege oder klarere Prompts."],
  [
    "low_confidence_rate",
    "Niedrige Sicherheit",
    "Niedrige Sicherheit ist ein Signal für Review oder Wissenslücken."
  ]
] as const;

type AdminAiEffectivenessProps = {
  readonly effectivenessState: AdminAiEffectivenessState;
};

/**
 * Render costs, quality and capability signals for Admin-AI.
 */
export function AdminAiEffectiveness({ effectivenessState }: AdminAiEffectivenessProps): ReactNode {
  const langfuse = langfuseStatus(effectivenessState);
  const safety = safetyStatus(effectivenessState);
  const safetyValues = safetyFields(effectivenessState);

  return (
    <>
      <section className="ai-admin-area" id="ai-costs">
        <div className="ai-admin-area-header">
          <div>
            <span className="section-kicker">4. Kosten & Effektivität</span>
            <h3>Was kostet die KI und wie gut wirkt sie?</h3>
            <p className="panel-meta">
              Kosten pro App-Nutzer werden mit Feedback, Quellenabdeckung und Antworten ohne Quellen
              zusammengeführt.
            </p>
          </div>
          <span className="badge badge-ai is-active">
            {effectivenessState.isLoading ? "Kosten werden geladen" : "Kosten geladen"}
          </span>
        </div>
        <div className="dashboard-grid dashboard-grid-4">
          {COST_KPIS.map(([key, label]) => (
            <article className="metric-card" key={key}>
              <span>{label}</span>
              <strong>{effectivenessKpiValue(effectivenessState, key)}</strong>
            </article>
          ))}
          <article className="metric-card">
            <span>Preisstatus</span>
            <strong>{priceStatusText(effectivenessState)}</strong>
          </article>
        </div>

        <section className="panel mt-4">
          <div className="panel-header">
            <div>
              <h3>Langfuse Kostenmetriken</h3>
              <p className="panel-meta">
                Direkt aus der Langfuse Metrics API, getrennt von der lokalen Kostenschätzung.
              </p>
            </div>
            <span className={`badge badge-ai ${langfuse.tone}`}>
              {langfuse.label}
            </span>
          </div>
          <div className="dashboard-grid dashboard-grid-4">
            {LANGFUSE_KPIS.map(([key, label]) => (
              <article className="metric-card" key={key}>
                <span>{label}</span>
                <strong>{langfuseMetricValue(effectivenessState, key)}</strong>
              </article>
            ))}
          </div>
          <div className="content-grid two-columns mt-4">
            <article>
              <h4>Modelle</h4>
              <MiniBarList
                emptyDetail="Metrics API liefert keine Zeilen."
                emptyLabel="Noch keine Langfuse-Modellkosten"
                rows={langfuseModelRows(effectivenessState)}
              />
            </article>
            <article>
              <h4>Workflows</h4>
              <MiniBarList
                emptyDetail="Metrics API liefert keine Zeilen."
                emptyLabel="Noch keine Langfuse-Workflowkosten"
                rows={langfuseWorkflowRows(effectivenessState)}
              />
            </article>
          </div>
        </section>

        <section className="panel mt-4">
          <div className="panel-header">
            <div>
              <h3>Effektivitätsdiagramme</h3>
              <p className="panel-meta">
                Kosten werden erst sinnvoll, wenn sie neben Nutzen, Quellenrate und Feedback stehen.
              </p>
            </div>
          </div>
          <div className="effectiveness-chart-grid">
            <article className="effectiveness-chart">
              <span>Kosten pro Workflow</span>
              <MiniBarList
                emptyDetail="Nach AI-Anfragen erscheinen hier Balken."
                emptyLabel="Noch keine Workflowkosten"
                rows={workflowCostRows(effectivenessState)}
              />
            </article>
            <article className="effectiveness-chart">
              <span>Antwortqualität</span>
              <div className="quality-donut">
                <strong>{helpfulRateText(effectivenessState)}</strong>
                <small>hilfreich</small>
              </div>
            </article>
            <article className="effectiveness-chart">
              <span>Risiko-Signale</span>
              <StatsList rows={effectivenessRiskRows(effectivenessState).map((row) => [row.label, row.value] as const)} />
            </article>
          </div>
        </section>

        <section className="panel mt-4">
          <div className="panel-header">
            <h3>Nutzerkosten</h3>
            <span className="panel-meta">Sortiert nach Kosten, Tokens und Events</span>
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <caption>AI-Kosten pro App-Nutzer</caption>
              <thead>
                <tr>
                  <th scope="col">Nutzer</th>
                  <th scope="col">Langfuse</th>
                  <th scope="col">Events</th>
                  <th scope="col">Tokens</th>
                  <th scope="col">Kosten</th>
                  <th scope="col">Fallback</th>
                  <th scope="col">Letzte Nutzung</th>
                </tr>
              </thead>
              <tbody>
                {effectivenessState.userCosts.length ? (
                  effectivenessState.userCosts.map((row) => (
                    <tr key={`${userCostCell(row, "username")}:${userCostCell(row, "latest_used_at")}`}>
                      <td>{userCostCell(row, "username")}</td>
                      <td>{userCostCell(row, "langfuse_user_id")}</td>
                      <td>{userCostCell(row, "events")}</td>
                      <td>{userCostCell(row, "total_tokens")}</td>
                      <td>{userCostCell(row, "estimated_cost_usd")}</td>
                      <td>{userCostCell(row, "fallback_rate")}</td>
                      <td>{userCostCell(row, "latest_used_at")}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={7}>
                      <div className="admin-empty">
                        <strong>Noch keine AI-Nutzung.</strong>
                        <span>Nach echten AI-Anfragen erscheinen hier Nutzerkosten.</span>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </section>

      <section className="ai-admin-area" id="ai-feedback">
        <div className="ai-admin-area-header">
          <div>
            <span className="section-kicker">6. KI-Feedback</span>
            <h3>Welche Feedback-, Sicherheit- und Ausweichbetrieb-Signale brauchen Review?</h3>
            <p className="panel-meta">
              Bewusst getrennte Sicht auf Antwortfeedback, unterstützte Fähigkeiten, gesperrte
              Aussagen, lokale Antworten und Risikosignale.
            </p>
          </div>
          <span className={`badge badge-ai ${safety.tone}`}>
            {safety.label}
          </span>
        </div>
        <section className="panel">
          <div className="panel-header">
            <div>
              <h3>Sicherheit & Ausweichbetrieb Momentaufnahme</h3>
              <p className="panel-meta">
                Aus bestehenden Summary-, Telemetry- und Observability-Daten abgeleitet.
              </p>
            </div>
            <span className={`status-pill ${safety.tone}`}>
              {safety.label}
            </span>
          </div>
          <div className="ai-safety-grid">
            {SAFETY_FIELDS.map(([key, label, detail]) => (
              <article className="ai-safety-card" key={key}>
                <span>{label}</span>
                <strong>
                  {safetyValues.find((item) => item.label === key)?.value ?? "0"}
                </strong>
                <small>{detail}</small>
              </article>
            ))}
          </div>
        </section>

        <div className="ai-capability-grid">
          {capabilityGroups().map((group) => (
            <section className="panel ai-capability-column" key={group.key}>
              <div className="panel-header">
                <h3>{capabilityTitle(group.key)}</h3>
                <span className={`status-pill ${group.tone}`}>{capabilityStatus(group.key)}</span>
              </div>
              <div className="stack">
                {group.items.map((item) => (
                  <article className={`ai-capability-card ${group.tone}`} key={item.label}>
                    <strong>{item.label}</strong>
                    <p>{item.value}</p>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
      </section>
    </>
  );
}
