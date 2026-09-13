import { useEffect, useMemo, useState } from "react";

import { readStoredSession } from "../auth/session";
import {
  deleteAdminUser,
  loadAdminUsers,
  loadEmployeeChoices,
  loadPermissionSchema,
  resetUserPassword,
  saveUserPermissions,
  setUserLockState,
  updateUserEmployee
} from "./adminUserApi";
import type {
  AdminEmployee,
  AdminPermission,
  AdminUser,
  MessageState,
  PermissionSchema
} from "./adminUserTypes";
import {
  adminUserErrorMessage,
  confirmAdminAction,
  permissionChangeSummary,
  requestPassword,
  schemaDashboardKeys,
  refreshCurrentUserIfNeeded
} from "./adminUserUtils";
import { type AdminUsersFiltersValue } from "./components/AdminUsersFilters";
import { useAdminUsersSidePanels } from "./useAdminUsersSidePanels";

type AdminUsersData = {
  readonly aiSummary: ReturnType<typeof useAdminUsersSidePanels>["aiSummary"];
  readonly auditEntries: ReturnType<typeof useAdminUsersSidePanels>["auditEntries"];
  readonly auditSearch: string;
  readonly backupMessage: MessageState;
  readonly backups: ReturnType<typeof useAdminUsersSidePanels>["backups"];
  readonly employees: readonly AdminEmployee[];
  readonly emptyText: string;
  readonly filters: AdminUsersFiltersValue;
  readonly latestEvents: ReturnType<typeof useAdminUsersSidePanels>["latestEvents"];
  readonly message: MessageState;
  readonly permissionDraft: Record<string, AdminPermission>;
  readonly permissionMessage: MessageState;
  readonly schema: PermissionSchema | null;
  readonly selectedUser: AdminUser | null;
  readonly setAuditSearch: (value: string) => void;
  readonly userMetrics: ReturnType<typeof useAdminUsersSidePanels>["userMetrics"];
  readonly users: readonly AdminUser[];
  readonly changeEmployee: (user: AdminUser, employeeId: string) => Promise<void>;
  readonly createBackupArchive: () => Promise<void>;
  readonly openPermissionEditor: (user: AdminUser) => void;
  readonly refreshAuditEntries: (query?: string) => Promise<void>;
  readonly removeUser: (user: AdminUser) => Promise<void>;
  readonly resetPassword: (user: AdminUser) => Promise<void>;
  readonly restoreBackupArchive: ReturnType<typeof useAdminUsersSidePanels>["restoreBackupArchive"];
  readonly submitPermissions: () => Promise<void>;
  readonly toggleLock: (user: AdminUser) => Promise<void>;
  readonly updateFilter: (field: keyof AdminUsersFiltersValue, value: string) => void;
  readonly updatePermission: (dashboard: string, action: keyof AdminPermission, value: boolean | string) => void;
};

/**
 * Return a local editable permission map for one user.
 */
function permissionDraftFor(schema: PermissionSchema | null, user: AdminUser): Record<string, AdminPermission> {
  return Object.fromEntries(
    schemaDashboardKeys(schema).map((dashboard) => [
      dashboard,
      {
        can_view: Boolean(user.permissions?.[dashboard]?.can_view),
        can_write: Boolean(user.permissions?.[dashboard]?.can_write),
        employee_access_level: user.permissions?.[dashboard]?.employee_access_level || "none"
      }
    ])
  );
}

/**
 * Return the current stored user id.
 */
function currentSessionUserId(): number | undefined {
  return readStoredSession().user?.id;
}

/**
 * Own Admin-User state, data loading and mutations for the React island.
 */
export function useAdminUsersData(): AdminUsersData {
  const sidePanels = useAdminUsersSidePanels();
  const [employees, setEmployees] = useState<AdminEmployee[]>([]);
  const [filters, setFilters] = useState<AdminUsersFiltersValue>({ q: "", role: "", status: "" });
  const [message, setMessage] = useState<MessageState>({ text: "Nutzer werden geladen...", error: false });
  const [permissionDraft, setPermissionDraft] = useState<Record<string, AdminPermission>>({});
  const [permissionMessage, setPermissionMessage] = useState<MessageState>({ text: "", error: false });
  const [schema, setSchema] = useState<PermissionSchema | null>(null);
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);

  const hasActiveFilters = Boolean(filters.q || filters.role || filters.status);

  /**
   * Refresh user rows and employee choices in parallel.
   */
  async function refreshUsers(nextFilters = filters): Promise<AdminUser[]> {
    setMessage({ text: "Nutzer werden geladen...", error: false });
    try {
      const [loadedUsers, loadedEmployees] = await Promise.all([
        loadAdminUsers(nextFilters),
        loadEmployeeChoices()
      ]);
      setUsers(loadedUsers);
      setEmployees(loadedEmployees);
      setMessage({ text: "", error: false });
      if (selectedUser) {
        const freshUser = loadedUsers.find((item) => item.id === selectedUser.id) || null;
        setSelectedUser(freshUser);
        if (freshUser) setPermissionDraft(permissionDraftFor(schema, freshUser));
      }
      return loadedUsers;
    } catch (error) {
      setUsers([]);
      setMessage({ text: adminUserErrorMessage(error), error: true });
      return [];
    }
  }

  /**
   * Update one filter field and refresh the list.
   */
  function updateFilter(field: keyof AdminUsersFiltersValue, value: string): void {
    const nextFilters = { ...filters, [field]: value };
    setFilters(nextFilters);
    void refreshUsers(nextFilters);
  }

  /**
   * Select one user for permission editing.
   */
  function openPermissionEditor(user: AdminUser): void {
    setSelectedUser(user);
    setPermissionDraft(permissionDraftFor(schema, user));
    setPermissionMessage({ text: "", error: false });
  }

  /**
   * Update one permission field in local editor state.
   */
  function updatePermission(dashboard: string, action: keyof AdminPermission, value: boolean | string): void {
    setPermissionDraft((current) => ({
      ...current,
      [dashboard]: {
        ...current[dashboard],
        [action]: value
      }
    }));
  }

  /**
   * Save the selected user's permissions after confirmation.
   */
  async function submitPermissions(): Promise<void> {
    if (!selectedUser) return;
    const changes = permissionChangeSummary(schema, selectedUser, permissionDraft);
    if (changes.length) {
      const confirmed = await confirmAdminAction("Diese Rechte speichern?", changes.join("\n"));
      if (!confirmed) return;
    }
    try {
      const updated = await saveUserPermissions(selectedUser.id, permissionDraft);
      await refreshCurrentUserIfNeeded(updated.id, currentSessionUserId());
      setSelectedUser(updated);
      setPermissionDraft(permissionDraftFor(schema, updated));
      setPermissionMessage({ text: "Rechte gespeichert.", error: false });
      await refreshUsers();
      await sidePanels.refreshAuditEntries();
    } catch (error) {
      setPermissionMessage({ text: adminUserErrorMessage(error), error: true });
    }
  }

  /**
   * Link one user to an employee record.
   */
  async function changeEmployee(user: AdminUser, employeeId: string): Promise<void> {
    try {
      const updated = await updateUserEmployee(user.id, employeeId);
      await refreshCurrentUserIfNeeded(updated.id, currentSessionUserId());
      await refreshUsers();
    } catch (error) {
      setPermissionMessage({ text: adminUserErrorMessage(error), error: true });
    }
  }

  /**
   * Reset one user's password through the shared app dialog.
   */
  async function resetPassword(user: AdminUser): Promise<void> {
    try {
      const password = await requestPassword("Passwort zurücksetzen", `Neues Passwort für ${user.username} vergeben.`);
      if (password === null) return;
      await resetUserPassword(user.id, password);
      setPermissionMessage({ text: "Passwort aktualisiert.", error: false });
      await sidePanels.refreshAuditEntries();
    } catch (error) {
      setPermissionMessage({ text: adminUserErrorMessage(error), error: true });
    }
  }

  /**
   * Lock or unlock one user account.
   */
  async function toggleLock(user: AdminUser): Promise<void> {
    try {
      await setUserLockState(user.id, user.is_active);
      setPermissionMessage({ text: user.is_active ? "User gesperrt." : "User entsperrt.", error: false });
      await refreshUsers();
      await sidePanels.refreshAuditEntries();
    } catch (error) {
      setPermissionMessage({ text: adminUserErrorMessage(error), error: true });
    }
  }

  /**
   * Delete one user after confirmation.
   */
  async function removeUser(user: AdminUser): Promise<void> {
    const confirmed = await confirmAdminAction(
      "User löschen",
      `${user.username} wirklich löschen? Diese Aktion kann nicht direkt rückgängig gemacht werden.`,
      "Löschen"
    );
    if (!confirmed) return;
    try {
      await deleteAdminUser(user.id);
      setPermissionMessage({ text: "User gelöscht.", error: false });
      await refreshUsers();
      await sidePanels.refreshAuditEntries();
    } catch (error) {
      setPermissionMessage({ text: adminUserErrorMessage(error), error: true });
    }
  }

  useEffect(() => {
    loadPermissionSchema()
      .then((loadedSchema) => {
        setSchema(loadedSchema);
        return refreshUsers();
      })
      .catch((error: unknown) => {
        setMessage({ text: adminUserErrorMessage(error), error: true });
      });
  }, []);

  const emptyText = useMemo(() => {
    if (message.text) return message.text;
    if (!users.length && hasActiveFilters) return "Keine Nutzer für diese Filter gefunden.";
    if (!users.length) return "Noch keine Nutzer vorhanden.";
    return "";
  }, [hasActiveFilters, message.text, users.length]);

  return {
    aiSummary: sidePanels.aiSummary,
    auditEntries: sidePanels.auditEntries,
    auditSearch: sidePanels.auditSearch,
    backupMessage: sidePanels.backupMessage,
    backups: sidePanels.backups,
    changeEmployee,
    createBackupArchive: sidePanels.createBackupArchive,
    employees,
    emptyText,
    filters,
    latestEvents: sidePanels.latestEvents,
    message,
    openPermissionEditor,
    permissionDraft,
    permissionMessage,
    refreshAuditEntries: sidePanels.refreshAuditEntries,
    removeUser,
    resetPassword,
    restoreBackupArchive: sidePanels.restoreBackupArchive,
    schema,
    selectedUser,
    setAuditSearch: sidePanels.setAuditSearch,
    submitPermissions,
    toggleLock,
    updateFilter,
    updatePermission,
    userMetrics: sidePanels.userMetrics,
    users
  };
}
