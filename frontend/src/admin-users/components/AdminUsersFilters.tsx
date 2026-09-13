import { type ReactNode } from "react";

import { ROLE_OPTIONS } from "../adminUserUtils";

export type AdminUsersFiltersValue = {
  readonly q: string;
  readonly role: string;
  readonly status: string;
};

type AdminUsersFiltersProps = {
  readonly filters: AdminUsersFiltersValue;
  readonly onFilterChange: (field: keyof AdminUsersFiltersValue, value: string) => void;
};

/**
 * Render the admin user list filters.
 */
export function AdminUsersFilters(props: AdminUsersFiltersProps): ReactNode {
  return (
    <div className="toolbar mb-4 flex flex-wrap gap-3">
      <input
        autoComplete="off"
        className="input input-bordered flex-1 min-w-48"
        onChange={(event) => props.onFilterChange("q", event.currentTarget.value)}
        placeholder="Nutzername oder E-Mail..."
        type="search"
        value={props.filters.q}
      />
      <select
        className="select select-bordered"
        onChange={(event) => props.onFilterChange("role", event.currentTarget.value)}
        value={props.filters.role}
      >
        <option value="">Alle Rollen</option>
        {ROLE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <select
        className="select select-bordered"
        onChange={(event) => props.onFilterChange("status", event.currentTarget.value)}
        value={props.filters.status}
      >
        <option value="">Alle Status</option>
        <option value="active">Aktiv</option>
        <option value="inactive">Gesperrt</option>
      </select>
    </div>
  );
}
