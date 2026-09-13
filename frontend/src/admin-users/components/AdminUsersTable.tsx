import { type ReactNode } from "react";

import type { AdminEmployee, AdminUser, MessageState } from "../adminUserTypes";
import { AdminUsersFilters, type AdminUsersFiltersValue } from "./AdminUsersFilters";

type AdminUsersTableProps = {
  readonly employees: readonly AdminEmployee[];
  readonly emptyText: string;
  readonly filters: AdminUsersFiltersValue;
  readonly message: MessageState;
  readonly onDelete: (user: AdminUser) => Promise<void>;
  readonly onEmployeeChange: (user: AdminUser, employeeId: string) => Promise<void>;
  readonly onFilterChange: (field: keyof AdminUsersFiltersValue, value: string) => void;
  readonly onPermissions: (user: AdminUser) => void;
  readonly onResetPassword: (user: AdminUser) => Promise<void>;
  readonly onToggleLock: (user: AdminUser) => Promise<void>;
  readonly users: readonly AdminUser[];
};

/**
 * Render filters and the user table.
 */
export function AdminUsersTable(props: AdminUsersTableProps): ReactNode {
  return (
    <article className="card app-card mobile-primary-card lg:col-span-12">
      <div className="card-body">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Nutzer suchen</h2>
            <p className="panel-meta">Nur für Master/Admin sichtbar</p>
          </div>
        </div>
        <AdminUsersFilters filters={props.filters} onFilterChange={props.onFilterChange} />
        <p className={`panel-meta py-6 text-center${props.message.error ? " is-error" : ""}`} hidden={props.users.length > 0}>{props.emptyText}</p>
        <div className="table-wrap" hidden={props.users.length === 0}>
          <table className="table data-table">
            <caption>Nutzerliste mit Rolle, Bereich, Status und Aktionen</caption>
            <thead>
              <tr>
                <th scope="col">Nutzer</th>
                <th scope="col">E-Mail</th>
                <th scope="col">Rolle</th>
                <th scope="col">Bereich</th>
                <th scope="col">Mitarbeiter</th>
                <th scope="col">Status</th>
                <th scope="col">Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {props.users.map((user) => (
                <tr key={user.id}>
                  <td>{user.username}</td>
                  <td>{user.email}</td>
                  <td>{user.role}</td>
                  <td>{user.department?.name || ""}</td>
                  <td>
                    <select className="select select-bordered" value={user.employee_id ? String(user.employee_id) : ""} onChange={(event) => void props.onEmployeeChange(user, event.currentTarget.value)}>
                      <option value="">Nicht verknüpft</option>
                      {props.employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.name} ({employee.personnel_number})</option>)}
                    </select>
                  </td>
                  <td>{user.is_active ? "aktiv" : "gesperrt"}</td>
                  <td>
                    <div className="table-actions">
                      <button className="btn btn-primary btn-sm" type="button" onClick={() => props.onPermissions(user)}>Rechte</button>
                      <button className="btn btn-outline btn-sm" type="button" onClick={() => void props.onResetPassword(user)}>Passwort</button>
                      <button className="btn btn-outline btn-sm" type="button" onClick={() => void props.onToggleLock(user)}>{user.is_active ? "Sperren" : "Entsperren"}</button>
                      <button className="btn btn-error btn-sm text-white" type="button" onClick={() => void props.onDelete(user)}>Löschen</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </article>
  );
}
