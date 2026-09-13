import type { ReactNode } from "react";

import { PageActionBar } from "../../components/ui/PageActionBar";
import { createActionDefinition } from "../../components/ui/createActionSchema";
import type { VacationRequest, VacationSummary } from "../vacationTypes";

type VacationHeaderProps = {
  readonly requests: readonly VacationRequest[];
  readonly selectedBalance: VacationSummary | null;
  readonly summaries: readonly VacationSummary[];
};

type VacationHeroProps = {
  readonly onRequestOpen: () => void;
};

/**
 * Render the vacations page hero.
 */
export function VacationHeader({ onRequestOpen }: VacationHeroProps): ReactNode {
  return (
    <section className="page-hero vacation-hero is-compact">
      <div>
        <h1 className="page-title">Urlaubsplanung</h1>
        <p className="page-description">
          Anträge, Vertreter, Schichtbezug und Auswirkungen auf den Betrieb in einer gemeinsamen Planungsansicht.
        </p>
      </div>
      <PageActionBar
        label="Urlaubsplanung Aktionen"
        actions={[
          { onClick: onRequestOpen, schema: createActionDefinition("vacationRequest"), variant: "primary" },
          { href: "#vacation-decisions", label: "Offene Anträge", variant: "outline" }
        ]}
      />
    </section>
  );
}

/**
 * Render vacation KPI cards.
 */
export function VacationStats({ requests, selectedBalance, summaries }: VacationHeaderProps): ReactNode {
  const pendingRequests = requests.filter((request) => request.status === "pending");
  const riskyRequests = requests.filter((request) => ["pending", "approved"].includes(request.status || "") && ["warning", "critical"].includes(request.impact_level || ""));
  const usedTotal = summaries.reduce((sum, summary) => sum + Number(summary.used || 0), 0);
  const pendingTotal = summaries.reduce((sum, summary) => sum + Number(summary.pending || 0), 0);

  return (
    <section className="vacation-control-strip" aria-label="Urlaubskennzahlen">
      <article className="vacation-control-stat is-warning">
        <span>Ausstehend</span>
        <strong data-vac-pending-count>{pendingRequests.length}</strong>
        <small>Anträge zur Entscheidung</small>
      </article>
      <article className="vacation-control-stat is-risk">
        <span>Konflikte</span>
        <strong data-vac-conflict-count>{riskyRequests.length}</strong>
        <small>Unterbesetzung oder Schichttreffer</small>
      </article>
      <article className="vacation-control-stat is-good">
        <span>Verfügbar</span>
        <strong data-vac-selected-available>{selectedBalance ? String(selectedBalance.available || 0) : "-"}</strong>
        <small>für ausgewählte Person</small>
      </article>
      <article className="vacation-control-stat is-info">
        <span>Genehmigt</span>
        <strong data-vac-used-total>{usedTotal || "-"}</strong>
        <small>genutzte Tage im Jahr</small>
      </article>
      <article className="vacation-control-stat is-muted">
        <span>Reserviert</span>
        <strong data-vac-pending-total>{pendingTotal || "-"}</strong>
        <small>durch offene Anträge</small>
      </article>
    </section>
  );
}
