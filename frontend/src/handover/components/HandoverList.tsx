import { type ReactNode } from "react";

import { HandoverCard } from "./HandoverCard";
import { HandoverFilters } from "./HandoverListFilters";
import type { HandoverFilters as HandoverFilterState, HandoverMessage, HandoverRecord, Machine } from "../handoverTypes";

type HandoverListProps = {
  readonly filters: HandoverFilterState;
  readonly handovers: readonly HandoverRecord[];
  readonly loadedCount: number;
  readonly machines: readonly Machine[];
  readonly message: HandoverMessage;
  readonly onComplete: (handover: HandoverRecord) => void;
  readonly onEdit: (handover: HandoverRecord) => void;
  readonly onFilter: () => void;
  readonly onFilterChange: (filters: HandoverFilterState) => void;
  readonly onResetFilters: () => void;
  readonly writable: boolean;
};

/**
 * Render the handover list and filters.
 */
export function HandoverList({
  filters,
  handovers,
  loadedCount,
  machines,
  message,
  onComplete,
  onEdit,
  onFilter,
  onFilterChange,
  onResetFilters,
  writable,
}: HandoverListProps): ReactNode {
  const summaryText = message.text || `${handovers.length} von ${loadedCount} Übergaben sichtbar`;

  return (
    <article className="handover-list-shell app-card" id="handover-list">
      <header className="handover-list-header">
        <div>
          <h2>Übergabe-Verlauf</h2>
          <p className="panel-meta">Nach Bereich, Datum, Schicht, Maschine oder Status filtern.</p>
        </div>
      </header>
      <HandoverFilters
        filters={filters}
        machines={machines}
        onFilter={onFilter}
        onFilterChange={onFilterChange}
        onResetFilters={onResetFilters}
      />
      <span className={`handover-filter-summary${message.isError ? " is-error" : ""}`} id="ho-filter-summary">
        {summaryText}
      </span>
      <div className="handover-card-grid" id="ho-list-wrap">
        {handovers.length ? (
          handovers.map((handover) => (
            <HandoverCard
              handover={handover}
              key={handover.id}
              onComplete={onComplete}
              onEdit={onEdit}
              writable={writable}
            />
          ))
        ) : (
          <p className="guided-empty-state" id="ho-empty">
            Keine Übergaben gefunden.
          </p>
        )}
      </div>
    </article>
  );
}
