import { type ReactNode } from "react";

import type { AdminAiBarRow } from "../adminAiEffectivenessModel";

/**
 * Render existing mini-bar rows with an empty fallback.
 */
export function MiniBarList({
  emptyDetail,
  emptyLabel,
  rows
}: {
  readonly emptyDetail: string;
  readonly emptyLabel: string;
  readonly rows: readonly AdminAiBarRow[];
}): ReactNode {
  return (
    <div className="mini-bar-list">
      {rows.length ? (
        rows.map((row) => (
          <div className="mini-bar-row" key={`${row.label}:${row.value}`}>
            <span>{row.label}</span>
            <i style={{ width: row.width }} />
            <strong>{row.value}</strong>
          </div>
        ))
      ) : (
        <div className="stat-row">
          <span>{emptyLabel}</span>
          <strong>{emptyDetail}</strong>
        </div>
      )}
    </div>
  );
}

/**
 * Return the visible title for one capability group.
 */
export function capabilityTitle(key: string): string {
  if (key === "supported") return "Unterstützt";
  if (key === "partial") return "Teilweise unterstützt";
  return "Nicht unterstützt";
}

/**
 * Return the visible status for one capability group.
 */
export function capabilityStatus(key: string): string {
  if (key === "supported") return "aktiv";
  if (key === "partial") return "abhängig von Daten";
  return "bewusst gesperrt";
}
