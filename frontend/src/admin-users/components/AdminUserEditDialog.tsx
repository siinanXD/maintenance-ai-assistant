import { type ReactNode } from "react";

import type { AdminPermission, AdminUser, MessageState, PermissionSchema } from "../adminUserTypes";
import { AdminUserRolePanel } from "./AdminUserRolePanel";

type PermissionEditorProps = {
  readonly draft: Record<string, AdminPermission>;
  readonly message: MessageState;
  readonly onPermissionChange: (dashboard: string, action: keyof AdminPermission, value: boolean | string) => void;
  readonly onSubmit: () => Promise<void>;
  readonly schema: PermissionSchema | null;
  readonly selectedUser: AdminUser | null;
};

/**
 * Render the selected user's permission editor.
 */
export function AdminUserEditDialog(props: PermissionEditorProps): ReactNode {
  if (!props.selectedUser || !props.schema) {
    return null;
  }
  const selectedUser = props.selectedUser;
  const schema = props.schema;
  return (
    <article className="card app-card mobile-secondary-card lg:col-span-12">
      <div className="card-body">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Cockpit-Rechte</h2>
            <p className="panel-meta">{selectedUser.username} - Rechte je Cockpit</p>
            <p className="panel-meta">Rollen-Default: {selectedUser.role} | Abweichungen werden vor dem Speichern angezeigt.</p>
          </div>
        </div>
        <form onSubmit={(event) => { event.preventDefault(); void props.onSubmit(); }}>
          <AdminUserRolePanel
            draft={props.draft}
            onPermissionChange={props.onPermissionChange}
            schema={schema}
            selectedUser={selectedUser}
          />
          <div className="toolbar form-actions">
            <button className="btn btn-primary" type="submit">Rechte speichern</button>
            <span className={`panel-meta${props.message.error ? " is-error" : ""}`}>{props.message.text}</span>
          </div>
        </form>
      </div>
    </article>
  );
}
