import { isValidElement, type ChangeEvent, type ReactNode, type ReactElement } from "react";

import { type AdminAiPayload } from "../adminAiApi";
import {
  type AdminAiTechnicalFilters,
  objectPayload
} from "../adminAiTechnicalModel";
import { ragText } from "../adminAiRagBoardModel";

/**
 * Render a metric grid with optional collapsed overflow cards.
 */
export function CollapsibleMetricGrid({
  cards,
  previewCount = 4,
  summaryLabel = "Weitere Metriken"
}: {
  readonly cards: readonly ReactElement[];
  readonly previewCount?: number;
  readonly summaryLabel?: string;
}): ReactNode {
  const previewCards = cards.slice(0, previewCount);
  const overflowCards = cards.slice(previewCount);

  return (
    <>
      <div className="dashboard-grid dashboard-grid-4 metric-grid-preview">{previewCards}</div>
      {overflowCards.length ? (
        <details className="help-disclosure ui-secondary-panel metric-grid-disclosure">
          <summary>
            {summaryLabel} ({overflowCards.length})
          </summary>
          <div className="help-disclosure-body">
            <div className="dashboard-grid dashboard-grid-4">{overflowCards}</div>
          </div>
        </details>
      ) : null}
    </>
  );
}

/**
 * Render one operations metric card.
 */
export function MetricCard({
  label,
  value
}: {
  readonly label: string;
  readonly value: unknown;
}): ReactNode {
  return (
    <article className="metric-card">
      <span>{label}</span>
      <strong>{ragText(value)}</strong>
    </article>
  );
}

/**
 * Render a compact metric row.
 */
export function StatRow({ label, value }: { readonly label: unknown; readonly value: unknown }): ReactNode {
  return (
    <div className="stat-row">
      <span>{ragText(label)}</span>
      <strong>{ragText(value)}</strong>
    </div>
  );
}

/**
 * Render label/value rows with an optional empty row.
 */
export function StatsList({
  empty,
  rows
}: {
  readonly empty?: readonly [unknown, unknown];
  readonly rows: readonly (readonly [unknown, unknown])[];
}): ReactNode {
  const visibleRows = rows.length ? rows : empty ? [empty] : [];

  return (
    <div className="stats-list">
      {visibleRows.map(([label, value], index) => (
        <StatRow key={`${ragText(label)}-${index}`} label={label} value={value} />
      ))}
    </div>
  );
}

/**
 * Render a data table with an empty-state row.
 */
export function DataTable({
  caption,
  headers,
  rows
}: {
  readonly caption: string;
  readonly headers: readonly string[];
  readonly rows: readonly (readonly unknown[])[];
}): ReactNode {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <caption>{caption}</caption>
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header} scope="col">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((row, index) => (
              <tr key={index}>
                {row.map((value, cellIndex) => (
                  <td key={cellIndex}>{isValidElement(value) ? value : ragText(value)}</td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={headers.length}>Keine Daten vorhanden.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Return input handlers for Technical filters.
 */
export function filterChange(
  onChange: (key: keyof AdminAiTechnicalFilters, value: string) => void,
  key: keyof AdminAiTechnicalFilters
) {
  return (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => onChange(key, event.target.value);
}

/**
 * Return true when an unknown value is an object payload.
 */
export function isPayload(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Return prompt-safe debug steps.
 */
export function debugSteps(item: AdminAiPayload | null): AdminAiPayload[] {
  const debug = objectPayload(item?.retrieval_debug || item?.debug);
  const steps = debug.decision_trace || item?.decision_trace || [];
  return Array.isArray(steps) ? steps.filter(isPayload) : [];
}

/**
 * Convert common list payloads into label/value rows.
 */
export function topList(value: unknown): readonly (readonly [unknown, unknown])[] {
  const items = Array.isArray(value) ? value.filter(isPayload) : [];

  return items.slice(0, 8).map((item) => [
    item.label || item.question || item.title || item.source || item.key || item.id,
    item.count || item.value || item.total || item.score || "-"
  ] as const);
}

/**
 * Return selectable debug requests.
 */
export function debugRequests(debugTools: AdminAiPayload): AdminAiPayload[] {
  const requests = debugTools.available_requests;
  return Array.isArray(requests) ? requests.filter(isPayload) : [];
}
