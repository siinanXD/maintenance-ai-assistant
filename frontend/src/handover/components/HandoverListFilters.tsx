import { type ReactNode } from "react";

import { DEPARTMENT_OPTIONS, SHIFT_OPTIONS } from "../handoverOptions";
import type { HandoverFilters, Machine } from "../handoverTypes";

type HandoverFiltersProps = {
  readonly filters: HandoverFilters;
  readonly machines: readonly Machine[];
  readonly onFilter: () => void;
  readonly onFilterChange: (filters: HandoverFilters) => void;
  readonly onResetFilters: () => void;
};

/**
 * Render a filter field wrapper.
 */
function FilterField({
  children,
  htmlFor,
  label,
}: {
  readonly children: ReactNode;
  readonly htmlFor: string;
  readonly label: string;
}): ReactNode {
  return (
    <label className="handover-filter-field" htmlFor={htmlFor}>
      <span>{label}</span>
      {children}
    </label>
  );
}

/**
 * Render the list filter controls.
 */
export function HandoverFilters({
  filters,
  machines,
  onFilter,
  onFilterChange,
  onResetFilters,
}: HandoverFiltersProps): ReactNode {
  return (
    <section className="handover-filter-bar" aria-label="Schichtübergaben filtern">
      <FilterField htmlFor="filter-search" label="Suche">
        <input
          className="input input-bordered input-sm"
          id="filter-search"
          placeholder="Maschine, Ursache, Folgeaufgabe"
          value={filters.search}
          onChange={(event) => onFilterChange({ ...filters, search: event.currentTarget.value })}
        />
      </FilterField>
      <FilterField htmlFor="filter-dept" label="Bereich">
        <select
          className="select select-bordered select-sm"
          id="filter-dept"
          value={filters.department}
          onChange={(event) => onFilterChange({ ...filters, department: event.currentTarget.value })}
        >
          <option value="">Alle Bereiche</option>
          {DEPARTMENT_OPTIONS.map((department) => (
            <option key={department.value} value={department.value}>
              {department.label}
            </option>
          ))}
        </select>
      </FilterField>
      <FilterField htmlFor="filter-date" label="Datum">
        <input
          className="input input-bordered input-sm"
          type="date"
          id="filter-date"
          value={filters.date}
          onChange={(event) => onFilterChange({ ...filters, date: event.currentTarget.value })}
        />
      </FilterField>
      <FilterField htmlFor="filter-shift" label="Schicht">
        <select
          className="select select-bordered select-sm"
          id="filter-shift"
          value={filters.shiftType}
          onChange={(event) => onFilterChange({ ...filters, shiftType: event.currentTarget.value })}
        >
          <option value="">Alle Schichten</option>
          {SHIFT_OPTIONS.map((shift) => (
            <option key={shift.value} value={shift.value}>
              {shift.label}
            </option>
          ))}
        </select>
      </FilterField>
      <FilterField htmlFor="filter-status" label="Status">
        <select
          className="select select-bordered select-sm"
          id="filter-status"
          value={filters.status}
          onChange={(event) => onFilterChange({ ...filters, status: event.currentTarget.value })}
        >
          <option value="">Alle</option>
          <option value="open">Offen</option>
          <option value="completed">Bestätigt</option>
        </select>
      </FilterField>
      <FilterField htmlFor="filter-machine" label="Maschine">
        <select
          className="select select-bordered select-sm"
          id="filter-machine"
          value={filters.machineId}
          onChange={(event) => onFilterChange({ ...filters, machineId: event.currentTarget.value })}
        >
          <option value="">Alle Maschinen</option>
          {machines.map((machine) => (
            <option key={machine.id} value={machine.id}>
              {machine.name}
            </option>
          ))}
        </select>
      </FilterField>
      <button className="btn btn-outline btn-sm" id="ho-filter-btn" type="button" onClick={onFilter}>
        Filtern
      </button>
      <button className="btn btn-ghost btn-sm" id="ho-filter-reset" type="button" onClick={onResetFilters}>
        Zurücksetzen
      </button>
    </section>
  );
}
