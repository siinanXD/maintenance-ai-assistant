import type { ReactNode } from "react";

import type { ErrorEntry } from "../errorTypes";
import { formatIncidentMinutes } from "../errorUtils";

type ErrorStatsProps = {
  readonly errors: readonly ErrorEntry[];
};

/**
 * Open incidents, how many of them are critical and the downtime they cause.
 */
export function ErrorStats({ errors }: ErrorStatsProps): ReactNode {
  const open = errors.filter((entry) => (entry.status || "open") !== "closed");
  const critical = open.filter((entry) => entry.severity === "critical" || entry.severity === "high").length;
  const downtime = open.reduce((sum, entry) => sum + Number(entry.downtime_minutes || 0), 0);

  return (
    <section className="incident-control-strip" aria-label="Störungskennzahlen">
      <article className="incident-control-stat is-open">
        <span>Offen</span>
        <strong data-error-open-count>{open.length}</strong>
        <small>von {errors.length} im Katalog</small>
      </article>
      <article className="incident-control-stat is-critical">
        <span>Kritisch</span>
        <strong data-error-critical-count>{critical}</strong>
        <small>offen mit hoher Schwere</small>
      </article>
      <article className="incident-control-stat is-downtime">
        <span>Stillstand</span>
        <strong data-error-downtime-count>{formatIncidentMinutes(downtime)}</strong>
        <small>durch offene Störungen</small>
      </article>
    </section>
  );
}
