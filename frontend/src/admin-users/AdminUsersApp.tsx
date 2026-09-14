import type { ReactNode } from "react";

import { PageHeader } from "../components/ui/PageHeader";
import { AdminUserEditDialog } from "./components/AdminUserEditDialog";
import { AiAnalyticsPanel, AuditLogPanel, BackupPanel } from "./components/AdminUsersSidePanels";
import { AdminUsersTable } from "./components/AdminUsersTable";
import { downloadBackup } from "./adminUserUtils";
import { useAdminUsersData } from "./useAdminUsersData";

/**
 * User administration: accounts, permissions, AI usage, audit log and backups.
 */
export function AdminUsersApp(): ReactNode {
  const adminUsers = useAdminUsersData();

  return (
    <>
      <PageHeader title="Nutzerverwaltung" description="Nutzer anzeigen, sperren, entsperren, Passwort zurücksetzen und löschen." />
      <section className="dashboard-grid">
        {adminUsers.aiSummary ? (
          <AiAnalyticsPanel
            latestEvents={adminUsers.latestEvents}
            summary={adminUsers.aiSummary}
            userMetrics={adminUsers.userMetrics}
          />
        ) : null}
        <AdminUserEditDialog
          draft={adminUsers.permissionDraft}
          message={adminUsers.permissionMessage}
          onPermissionChange={adminUsers.updatePermission}
          onSubmit={adminUsers.submitPermissions}
          schema={adminUsers.schema}
          selectedUser={adminUsers.selectedUser}
        />
        <AuditLogPanel
          auditEntries={adminUsers.auditEntries}
          auditSearch={adminUsers.auditSearch}
          onAuditRefresh={() => adminUsers.refreshAuditEntries()}
          onAuditSearch={adminUsers.setAuditSearch}
        />
        <BackupPanel
          backups={adminUsers.backups}
          message={adminUsers.backupMessage}
          onCreate={adminUsers.createBackupArchive}
          onDownload={(backup) => downloadBackup(backup.download_url, backup.filename)}
          onRestore={adminUsers.restoreBackupArchive}
        />
        <AdminUsersTable
          emptyText={adminUsers.emptyText}
          employees={adminUsers.employees}
          filters={adminUsers.filters}
          message={adminUsers.message}
          onDelete={adminUsers.removeUser}
          onEmployeeChange={adminUsers.changeEmployee}
          onFilterChange={adminUsers.updateFilter}
          onPermissions={adminUsers.openPermissionEditor}
          onResetPassword={adminUsers.resetPassword}
          onToggleLock={adminUsers.toggleLock}
          users={adminUsers.users}
        />
      </section>
    </>
  );
}
