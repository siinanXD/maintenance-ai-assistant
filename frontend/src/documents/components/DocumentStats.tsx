import type { ReactNode } from "react";

import type { GeneratedDocument, MachineManual } from "../documentTypes";

type DocumentStatsProps = {
  readonly documents: readonly GeneratedDocument[];
  readonly manuals: readonly MachineManual[];
};

/**
 * Render document KPI cards.
 */
export function DocumentStats({ documents, manuals }: DocumentStatsProps): ReactNode {
  return (
    <section className="surface-stat-grid" aria-label="Dokumentenstatus">
      <article className="surface-stat-card is-primary">
        <span>Berichte</span>
        <strong data-document-count>{documents.length} Dokumente</strong>
        <small>Generierte Wartungsberichte mit Prüf- und Versionsstatus.</small>
      </article>
      <article className="surface-stat-card is-ai">
        <span>Handbücher</span>
        <strong data-manual-count>{manuals.length} Handbücher</strong>
        <small>Maschinenwissen für Suche, Analyse und Quellenangaben.</small>
      </article>
    </section>
  );
}
