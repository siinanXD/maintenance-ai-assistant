import { useEffect, useState } from "react";

import {
  createBackup,
  loadAiSummary,
  loadAuditEntries,
  loadBackups,
  restoreBackup
} from "./adminUserApi";
import type { AiEvent, AiSummary, AiUserMetric, AuditEntry, BackupEntry, MessageState } from "./adminUserTypes";
import { adminUserErrorMessage, confirmAdminAction } from "./adminUserUtils";

type AdminUsersSidePanelsData = {
  readonly aiSummary: AiSummary | null;
  readonly auditEntries: readonly AuditEntry[];
  readonly auditSearch: string;
  readonly backupMessage: MessageState;
  readonly backups: readonly BackupEntry[];
  readonly latestEvents: readonly AiEvent[];
  readonly setAuditSearch: (value: string) => void;
  readonly userMetrics: readonly AiUserMetric[];
  readonly createBackupArchive: () => Promise<void>;
  readonly refreshAuditEntries: (query?: string) => Promise<void>;
  readonly restoreBackupArchive: (backup: BackupEntry) => Promise<void>;
};

/**
 * Own the Admin-Users AI summary, audit log and backup panels.
 */
export function useAdminUsersSidePanels(): AdminUsersSidePanelsData {
  const [aiSummary, setAiSummary] = useState<AiSummary | null>(null);
  const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([]);
  const [auditSearch, setAuditSearch] = useState("");
  const [backups, setBackups] = useState<BackupEntry[]>([]);
  const [backupMessage, setBackupMessage] = useState<MessageState>({ text: "", error: false });

  const latestEvents = aiSummary?.latest_events || [];
  const userMetrics = aiSummary?.user_metrics || [];

  /**
   * Refresh the audit log panel.
   */
  async function refreshAuditEntries(query = auditSearch): Promise<void> {
    try {
      setAuditEntries(await loadAuditEntries(query));
    } catch {
      setAuditEntries([]);
    }
  }

  /**
   * Refresh the backup list.
   */
  async function refreshBackups(): Promise<void> {
    try {
      setBackups(await loadBackups());
    } catch (error) {
      setBackupMessage({ text: adminUserErrorMessage(error), error: true });
    }
  }

  /**
   * Refresh AI and backup side panels independently.
   * The audit log loads through the search effect below, also on mount.
   */
  async function refreshSidePanels(): Promise<void> {
    await Promise.all([
      loadAiSummary().then(setAiSummary).catch(() => setAiSummary(null)),
      refreshBackups()
    ]);
  }

  /**
   * Create a backup and refresh the panel.
   */
  async function createBackupArchive(): Promise<void> {
    setBackupMessage({ text: "Backup wird erstellt...", error: false });
    try {
      await createBackup();
      setBackupMessage({ text: "Backup erstellt.", error: false });
      await refreshBackups();
      await refreshAuditEntries();
    } catch (error) {
      setBackupMessage({ text: adminUserErrorMessage(error), error: true });
    }
  }

  /**
   * Restore one backup after confirmation.
   */
  async function restoreBackupArchive(backup: BackupEntry): Promise<void> {
    const confirmed = await confirmAdminAction(
      "Backup wiederherstellen?",
      "Vor dem Restore wird automatisch ein Sicherheitsbackup erstellt.",
      "Restore"
    );
    if (!confirmed) return;
    setBackupMessage({ text: "Restore läuft...", error: false });
    try {
      await restoreBackup(backup.id);
      setBackupMessage({ text: "Backup wiederhergestellt.", error: false });
      await refreshBackups();
      await refreshAuditEntries();
    } catch (error) {
      setBackupMessage({ text: adminUserErrorMessage(error), error: true });
    }
  }

  useEffect(() => {
    void refreshSidePanels();
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void refreshAuditEntries(auditSearch);
    }, 300);
    return () => window.clearTimeout(timeoutId);
  }, [auditSearch]);

  return {
    aiSummary,
    auditEntries,
    auditSearch,
    backupMessage,
    backups,
    createBackupArchive,
    latestEvents,
    refreshAuditEntries,
    restoreBackupArchive,
    setAuditSearch,
    userMetrics
  };
}
