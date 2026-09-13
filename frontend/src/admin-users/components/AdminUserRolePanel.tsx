import { type ReactNode } from "react";

import type { AdminPermission, AdminUser, PermissionSchema } from "../adminUserTypes";
import {
  dashboardLabel,
  employeeAccessLabel,
  permissionSummary,
  roleDefaultPermission
} from "../adminUserUtils";

type AdminUserRolePanelProps = {
  readonly draft: Record<string, AdminPermission>;
  readonly onPermissionChange: (dashboard: string, action: keyof AdminPermission, value: boolean | string) => void;
  readonly schema: PermissionSchema;
  readonly selectedUser: AdminUser;
};

/**
 * Render the selected user's role and dashboard permission matrix.
 */
export function AdminUserRolePanel(props: AdminUserRolePanelProps): ReactNode {
  return (
    <div className="table-wrap">
      <table className="table data-table">
        <caption>Cockpit-Rechte für den ausgewählten Nutzer</caption>
        <thead>
          <tr>
            <th scope="col">Cockpit</th>
            <th scope="col">Anzeigen</th>
            <th scope="col">Bearbeiten</th>
            <th scope="col">Mitarbeiterdaten</th>
          </tr>
        </thead>
        <tbody>
          {props.schema.groups.map((group) => (
            <PermissionGroupRows
              draft={props.draft}
              group={group}
              key={group.key}
              onPermissionChange={props.onPermissionChange}
              schema={props.schema}
              selectedUser={props.selectedUser}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

type PermissionGroupRowsProps = {
  readonly draft: Record<string, AdminPermission>;
  readonly group: { readonly label: string; readonly dashboards: readonly string[] };
  readonly onPermissionChange: (dashboard: string, action: keyof AdminPermission, value: boolean | string) => void;
  readonly schema: PermissionSchema;
  readonly selectedUser: AdminUser;
};

/**
 * Render one permission group and its dashboard rows.
 */
function PermissionGroupRows(props: PermissionGroupRowsProps): ReactNode {
  return (
    <>
      <tr>
        <td className="panel-meta" colSpan={4}>{props.group.label}</td>
      </tr>
      {props.group.dashboards.map((dashboard) => {
        const permission = props.draft[dashboard] || {};
        const defaultPermission = roleDefaultPermission(props.schema, props.selectedUser.role, dashboard);
        const isAdminUsersDashboard = dashboard === "admin_users";
        const isMasterAdmin = props.selectedUser.role === "master_admin";
        const disabled = isAdminUsersDashboard;
        return (
          <tr key={dashboard}>
            <td>
              <div>
                <strong>{dashboardLabel(props.schema, dashboard)}</strong>
                <p className="panel-meta">Default: {permissionSummary(props.schema, defaultPermission)}</p>
              </div>
            </td>
            <td>
              <input
                checked={isAdminUsersDashboard ? isMasterAdmin : Boolean(permission.can_view)}
                disabled={disabled}
                onChange={(event) => props.onPermissionChange(dashboard, "can_view", event.currentTarget.checked)}
                type="checkbox"
              />
            </td>
            <td>
              <input
                checked={isAdminUsersDashboard ? isMasterAdmin : Boolean(permission.can_write)}
                disabled={disabled}
                onChange={(event) => props.onPermissionChange(dashboard, "can_write", event.currentTarget.checked)}
                type="checkbox"
              />
            </td>
            <td>
              {dashboard === "employees" ? (
                <select
                  className="select select-bordered"
                  onChange={(event) => props.onPermissionChange(dashboard, "employee_access_level", event.currentTarget.value)}
                  value={permission.employee_access_level || "none"}
                >
                  {props.schema.employee_access_levels.map((level) => <option key={level.key} value={level.key}>{employeeAccessLabel(props.schema, level.key)}</option>)}
                </select>
              ) : "-"}
            </td>
          </tr>
        );
      })}
    </>
  );
}
