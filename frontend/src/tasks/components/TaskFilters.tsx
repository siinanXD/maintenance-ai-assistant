import type { ReactNode } from "react";

import type { TaskFilters } from "../taskTypes";

type TaskFiltersProps = {
  readonly departments: readonly string[];
  readonly filters: TaskFilters;
  readonly total: number;
  readonly visible: number;
  readonly onFiltersChange: (filters: TaskFilters) => void;
};

/**
 * Render the task board filter bar.
 */
export function TaskFiltersBar({
  departments,
  filters,
  total,
  visible,
  onFiltersChange
}: TaskFiltersProps): ReactNode {
  /**
   * Update one filter field.
   */
  function updateFilter(fieldName: keyof TaskFilters, value: string): void {
    onFiltersChange({ ...filters, [fieldName]: value } as TaskFilters);
  }

  /**
   * Reset all task filters.
   */
  function resetFilters(): void {
    onFiltersChange({ search: "", status: "", priority: "", department: "", due: "" });
  }

  return (
    <section className="task-filter-bar" aria-label="Aufgaben filtern">
      <label className="task-filter-field" htmlFor="react-task-list-search">
        <span>Suche</span>
        <input
          className="input input-bordered input-sm"
          id="react-task-list-search"
          onChange={(event) => updateFilter("search", event.target.value)}
          placeholder="Titel, Maschine, Bereich, Status"
          value={filters.search}
        />
      </label>
      <label className="task-filter-field" htmlFor="react-task-status-filter">
        <span>Status</span>
        <select className="select select-bordered select-sm" id="react-task-status-filter" onChange={(event) => updateFilter("status", event.target.value)} value={filters.status}>
          <option value="">Alle</option>
          <option value="open">Offen</option>
          <option value="in_progress">In Arbeit</option>
          <option value="done">Erledigt</option>
          <option value="cancelled">Abgebrochen</option>
        </select>
      </label>
      <label className="task-filter-field" htmlFor="react-task-priority-filter">
        <span>Priorität</span>
        <select className="select select-bordered select-sm" id="react-task-priority-filter" onChange={(event) => updateFilter("priority", event.target.value)} value={filters.priority}>
          <option value="">Alle</option>
          <option value="urgent">Kritisch</option>
          <option value="soon">Bald</option>
          <option value="normal">Normal</option>
        </select>
      </label>
      <label className="task-filter-field" htmlFor="react-task-department-filter">
        <span>Bereich</span>
        <select className="select select-bordered select-sm" id="react-task-department-filter" onChange={(event) => updateFilter("department", event.target.value)} value={filters.department}>
          <option value="">Alle Bereiche</option>
          {departments.map((department) => (
            <option key={department} value={department}>{department}</option>
          ))}
        </select>
      </label>
      <label className="task-filter-field" htmlFor="react-task-due-filter">
        <span>Fälligkeit</span>
        <select className="select select-bordered select-sm" id="react-task-due-filter" onChange={(event) => updateFilter("due", event.target.value)} value={filters.due}>
          <option value="">Alle</option>
          <option value="overdue">Überfällig</option>
          <option value="today">Heute</option>
          <option value="planned">Geplant</option>
        </select>
      </label>
      <button className="btn btn-ghost btn-sm" onClick={resetFilters} type="button">
        Zurücksetzen
      </button>
      <span className="task-filter-summary">
        {total ? `${visible} von ${total} Aufgaben sichtbar` : "Noch keine Aufgaben vorhanden."}
      </span>
    </section>
  );
}
