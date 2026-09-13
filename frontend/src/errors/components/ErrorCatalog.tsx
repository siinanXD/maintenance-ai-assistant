import type { ReactNode } from "react";

import { closeErrorEntry, deleteErrorEntry, loadSimilarErrors } from "../errorApi";
import type { ErrorEntry, ErrorFilters, MessageState, SimilarErrorResult } from "../errorTypes";
import {
  QUICK_FILTERS,
  categoriesFromErrors,
  errorMatchesFilters,
  errorSeverityClass,
  errorSeverityLabel,
  errorStatusClass,
  errorStatusLabel,
  formatIncidentMinutes,
  incidentDate
} from "../errorUtils";

type ErrorCatalogProps = {
  readonly errors: readonly ErrorEntry[];
  readonly filters: ErrorFilters;
  readonly onEdit: (entry: ErrorEntry) => void;
  readonly onFiltersChange: (filters: ErrorFilters) => void;
  readonly onMessageChange: (message: MessageState) => void;
  readonly onMutated: () => Promise<void>;
  readonly onSimilarResult: (result: SimilarErrorResult) => void;
  readonly writable: boolean;
};

/**
 * Render one highlighted knowledge block.
 */
function HighlightedBlock({ label, value, variant }: { readonly label: string; readonly value?: string; readonly variant: string }): ReactNode {
  return (
    <div className={`knowledge-block ${variant}`}>
      <span>{label}</span>
      <strong>{value || "-"}</strong>
    </div>
  );
}

/**
 * Render one error card action button set.
 */
function ErrorCardActions(props: {
  readonly entry: ErrorEntry;
  readonly onEdit: (entry: ErrorEntry) => void;
  readonly onMessageChange: (message: MessageState) => void;
  readonly onMutated: () => Promise<void>;
  readonly onSimilarResult: (result: SimilarErrorResult) => void;
  readonly writable: boolean;
}): ReactNode {
  const status = props.entry.status || "open";

  /**
   * Load similar errors for the selected card.
   */
  async function handleSimilar(): Promise<void> {
    const text = [
      props.entry.title,
      props.entry.symptoms || props.entry.description,
      props.entry.possible_causes,
      props.entry.solution,
      props.entry.impact
    ].filter(Boolean).join(" ");
    props.onSimilarResult(await loadSimilarErrors(text, props.entry.machine || ""));
  }

  /**
   * Close the selected error.
   */
  async function handleClose(): Promise<void> {
    try {
      await closeErrorEntry(props.entry.id);
      await props.onMutated();
      props.onMessageChange({ text: "Störung geschlossen.", error: false });
    } catch (error) {
      props.onMessageChange({ text: error instanceof Error ? error.message : "Störung konnte nicht geschlossen werden.", error: true });
    }
  }

  /**
   * Delete the selected error after confirmation.
   */
  async function handleDelete(): Promise<void> {
    if (!window.confirm(`Fehler '${props.entry.title || props.entry.error_code || props.entry.id}' wirklich löschen?`)) return;
    try {
      await deleteErrorEntry(props.entry.id);
      await props.onMutated();
      props.onMessageChange({ text: "Störung gelöscht.", error: false });
    } catch (error) {
      props.onMessageChange({ text: error instanceof Error ? error.message : "Störung konnte nicht gelöscht werden.", error: true });
    }
  }

  return (
    <div className="error-card-actions">
      <button className="btn btn-outline btn-sm" type="button" onClick={handleSimilar}>Ähnliche Fehler finden</button>
      {props.writable && status !== "closed" ? <button className="btn btn-outline btn-sm" type="button" onClick={handleClose}>Schließen</button> : null}
      {props.writable ? <button className="btn btn-outline btn-sm" type="button" onClick={() => props.onEdit(props.entry)}>Bearbeiten</button> : null}
      {props.writable ? <button className="btn btn-ghost btn-sm" type="button" onClick={handleDelete}>Löschen</button> : null}
    </div>
  );
}

/**
 * Render one incident catalog card.
 */
function ErrorCard(props: ErrorCatalogProps & { readonly entry: ErrorEntry }): ReactNode {
  const status = props.entry.status || "open";
  const severity = props.entry.severity || "medium";

  return (
    <article className={`error-card incident-card is-status-${status} is-severity-${severity}`} data-search-text={props.entry.title || ""}>
      <div className="error-card-header">
        <div>
          <h3 className="error-card-title">{props.entry.title || "Unbenannter Fehler"}</h3>
          <div className="error-card-meta">
            {[props.entry.machine || "Maschine offen", props.entry.department?.name, props.entry.cause_category || "Kategorie offen"].filter(Boolean).map((value) => <span key={value}>{value}</span>)}
          </div>
        </div>
        <div className="incident-card-badges">
          <span className="badge status-badge is-open">{props.entry.error_code || "CODE"}</span>
          <span className={errorStatusClass(status)}>{errorStatusLabel(status)}</span>
          <span className={errorSeverityClass(severity)}>{errorSeverityLabel(severity)}</span>
        </div>
      </div>
      <div className="incident-card-metrics">
        {[
          ["Stillstand", formatIncidentMinutes(props.entry.downtime_minutes)],
          ["Verlust", formatIncidentMinutes(props.entry.production_loss_minutes)],
          ["Wiederholt", String(Number(props.entry.repeat_count || 0))],
          [status === "closed" ? "Geschlossen" : "Zuletzt",incidentDate(props.entry.closed_at || props.entry.last_seen_at || props.entry.created_at)]
        ].map(([label, value]) => (
          <span key={label}>
            <small>{label}</small>
            <strong>{value}</strong>
          </span>
        ))}
      </div>
      <div className="error-card-blocks">
        <HighlightedBlock label="Symptome" value={props.entry.symptoms || props.entry.description} variant="is-symptom" />
        <HighlightedBlock label="Ursache" value={props.entry.possible_causes} variant="is-cause" />
        <HighlightedBlock label="Lösung" value={props.entry.solution} variant="is-solution" />
        <HighlightedBlock label="Auswirkung" value={props.entry.impact} variant="is-impact" />
      </div>
      <ErrorCardActions {...props} />
    </article>
  );
}

/**
 * Render the searchable error catalog.
 */
export function ErrorCatalog(props: ErrorCatalogProps): ReactNode {
  const categories = categoriesFromErrors(props.errors);
  const visibleErrors = props.errors.filter((entry) => errorMatchesFilters(entry, props.filters));

  /**
   * Reset all catalog filters.
   */
  function resetFilters(): void {
    props.onFiltersChange({ search: "", status: "", severity: "", category: "", quick: "all" });
  }

  /**
   * Load similar errors from the current search or first catalog row.
   */
  async function findSimilarFromSearch(): Promise<void> {
    const first = props.errors[0];
    const text = props.filters.search.trim() || [first?.title, first?.possible_causes].filter(Boolean).join(" ");
    if (!text) {
      document.querySelector<HTMLInputElement>("[data-error-search]")?.focus();
      return;
    }
    props.onSimilarResult(await loadSimilarErrors(text));
  }

  return (
    <article className="incident-catalog-shell app-card" id="error-list">
      <header className="incident-catalog-header">
        <div>
          <p className="section-kicker">Katalog</p>
          <h2>Fehlerkatalog durchsuchen</h2>
          <p className="panel-meta">Code, Maschine, Symptom, Ursache, Lösung oder Auswirkung finden.</p>
        </div>
        <button className="btn btn-outline btn-sm" data-error-similar-focus type="button" onClick={findSimilarFromSearch}>Ähnliche Fehler finden</button>
      </header>
      <div className="incident-catalog-search">
        <label className="compact-search-field" htmlFor="error-search">
          <span>Suche im Katalog</span>
          <input
            className="input input-bordered input-sm"
            data-error-search
            id="error-search"
            placeholder="E104, Presse 3, Hydraulik, Sensor"
            value={props.filters.search}
            onChange={(event) => props.onFiltersChange({ ...props.filters, search: event.currentTarget.value })}
          />
        </label>
        <span className="incident-filter-summary" data-error-filter-summary>
          {visibleErrors.length} von {props.errors.length} Einträgen sichtbar
        </span>
      </div>
      <details className="help-disclosure ui-secondary-panel incident-filter-disclosure">
        <summary>Erweiterte Filter und Kategorien</summary>
        <div className="help-disclosure-body">
          <section className="incident-filter-bar" aria-label="Fehlerkatalog filtern">
            <label className="incident-filter-field" htmlFor="error-status-filter">
              <span>Status</span>
              <select className="select select-bordered select-sm" data-error-status-filter id="error-status-filter" value={props.filters.status} onChange={(event) => props.onFiltersChange({ ...props.filters, status: event.currentTarget.value })}>
                <option value="">Alle</option>
                <option value="open">Offen</option>
                <option value="in_progress">In Bearbeitung</option>
                <option value="closed">Geschlossen</option>
              </select>
            </label>
            <label className="incident-filter-field" htmlFor="error-severity-filter">
              <span>Schwere</span>
              <select className="select select-bordered select-sm" data-error-severity-filter id="error-severity-filter" value={props.filters.severity} onChange={(event) => props.onFiltersChange({ ...props.filters, severity: event.currentTarget.value })}>
                <option value="">Alle</option>
                <option value="critical">Kritisch</option>
                <option value="high">Hoch</option>
                <option value="medium">Mittel</option>
                <option value="low">Niedrig</option>
              </select>
            </label>
            <label className="incident-filter-field" htmlFor="error-category-filter">
              <span>Kategorie</span>
              <select className="select select-bordered select-sm" data-error-category-filter id="error-category-filter" value={props.filters.category} onChange={(event) => props.onFiltersChange({ ...props.filters, category: event.currentTarget.value })}>
                <option value="">Alle Kategorien</option>
                {categories.map((category) => <option key={category} value={category}>{category}</option>)}
              </select>
            </label>
            <button className="btn btn-ghost btn-sm" data-error-filter-reset type="button" onClick={resetFilters}>Zurücksetzen</button>
          </section>
          <div className="filter-chip-row incident-category-chips" aria-label="Schnellfilter Fehlerkatalog">
            <button className={`filter-chip${props.filters.quick === "all" ? " is-active" : ""}`} data-error-filter="all" type="button" onClick={() => props.onFiltersChange({ ...props.filters, quick: "all" })}>Alle</button>
            {QUICK_FILTERS.map((filter) => (
              <button className={`filter-chip${props.filters.quick === filter ? " is-active" : ""}`} data-error-filter={filter} key={filter} type="button" onClick={() => props.onFiltersChange({ ...props.filters, quick: filter })}>{filter}</button>
            ))}
          </div>
        </div>
      </details>
      <div className="error-card-grid incident-card-grid" data-error-list>
        {visibleErrors.length ? visibleErrors.map((entry) => <ErrorCard {...props} entry={entry} key={entry.id} />) : (
          <div className="guided-empty-state">
            <strong>Keine passenden Fehler gefunden</strong>
            <p>Beispielsuche: Fehlercode, Maschine oder Symptom. Wenn es ein neuer Fall ist, lege ihn mit Ursache und Lösung im Katalog an.</p>
          </div>
        )}
      </div>
    </article>
  );
}
