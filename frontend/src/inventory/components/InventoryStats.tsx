import type { ReactNode } from "react";

import type { InventoryMaterial } from "../inventoryTypes";
import { inventoryStats } from "../inventoryUtils";

type InventoryStatsProps = {
  readonly materials: readonly InventoryMaterial[];
};

/**
 * Render inventory KPI cards.
 */
export function InventoryStats({ materials }: InventoryStatsProps): ReactNode {
  const stats = inventoryStats(materials);

  return (
    <section className="surface-stat-grid ux-ops-summary-grid" aria-label="Lagerstatus">
      <article className="surface-stat-card is-primary">
        <span>Positionen</span>
        <strong data-inventory-count>{stats.count}</strong>
        <small>Materialien, Hersteller und Maschinenzuordnung.</small>
      </article>
      <article className="surface-stat-card is-warning">
        <span>Mindestbestand</span>
        <strong data-inventory-low-count>{stats.lowStock}</strong>
        <small>Positionen auf oder unter ihrem Mindestbestand.</small>
      </article>
      <article className="surface-stat-card is-ai">
        <span>Lagerwert</span>
        <strong data-inventory-total-value>{stats.totalValue}</strong>
        <small>Summierter Wert aus Bestand und Einzelkosten.</small>
      </article>
    </section>
  );
}
