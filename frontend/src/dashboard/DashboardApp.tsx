import { useCallback, useEffect, useState, type ReactNode } from "react";

import { markIslandMounted } from "../app/islandMount";
import { safeErrorMessage } from "../utils/errors";
import {
  completeDashboardTask,
  createDashboardTask,
  loadDashboardCoreData,
  loadDashboardInsightData,
  loadDashboardTask,
  startDashboardTask,
  suggestDashboardTask,
  updateDashboardTask,
  type DashboardPayload,
  type DashboardShiftCalendar,
  type DashboardTaskMutation,
  type DashboardTaskReportPayload
} from "./dashboardApi";
import { DashboardMarkup } from "./DashboardMarkup";
import { EMPTY_DASHBOARD_VIEW_STATE, type DashboardViewState } from "./dashboardModel";
import { employeesToShiftCalendar } from "./dashboardShiftModel";
import { taskDraftFromSuggestion } from "./dashboardTaskDraftModel";

const DASHBOARD_ISLAND = {
  mountedFlag: "maintenanceDashboardReactMounted",
  mountEvent: "maintenance-dashboard-react-mounted"
} as const;

declare global {
  interface Window {
    maintenanceDashboardReactAssetsOwned?: boolean;
    maintenanceDashboardReactOperationsOwned?: boolean;
    maintenanceDashboardReactPeopleOwned?: boolean;
    maintenanceDashboardReactShiftOwned?: boolean;
    maintenanceDashboardReactSideOwned?: boolean;
    maintenanceDashboardReactTasksOwned?: boolean;
    maintenanceDashboardReactTechnicalOwned?: boolean;
    maintenanceDashboardReactDraftOwned?: boolean;
  }
}

/**
 * Render the dashboard with React-owned markup and initial React data loading.
 */
export function DashboardApp(): ReactNode {
  const [dashboardState, setDashboardState] = useState<DashboardViewState>(EMPTY_DASHBOARD_VIEW_STATE);
  const [activeTask, setActiveTask] = useState<DashboardPayload | null>(null);
  const [isTaskBusy, setIsTaskBusy] = useState(false);
  const [isShiftCalendarLoading, setIsShiftCalendarLoading] = useState(true);
  const [shiftCalendar, setShiftCalendar] = useState<DashboardShiftCalendar | null>(null);
  const [taskMessage, setTaskMessage] = useState("");
  const [cockpitMessage, setCockpitMessage] = useState("");
  const [draftTask, setDraftTask] = useState<DashboardTaskMutation | null>(null);
  const [isDraftBusy, setIsDraftBusy] = useState(false);
  const [suggestText, setSuggestText] = useState("");

  const refreshDashboardData = useCallback(async (signal?: AbortSignal): Promise<void> => {
    setDashboardState((currentState) => ({
      ...currentState,
      errorMessage: "",
      isInsightLoading: true,
      isLoading: true
    }));

    // Operational data first: the cockpit becomes usable in well under a second.
    // AI insights (briefing with retrieval and AI prioritization) follow and may
    // take several seconds; they must never hold back the rest of the page.
    const insightPromise = loadDashboardInsightData(signal);
    const core = await loadDashboardCoreData(signal);
    if (signal?.aborted) return;
    setDashboardState((currentState) => ({
      data: { ...currentState.data, ...core, loadErrors: core.loadErrors },
      errorMessage: core.loadErrors.join(" | "),
      isInsightLoading: true,
      isLoading: false
    }));

    const insight = await insightPromise;
    if (signal?.aborted) return;
    setDashboardState((currentState) => {
      const loadErrors = [...currentState.data.loadErrors, ...insight.loadErrors];
      return {
        data: { ...currentState.data, ...insight, loadErrors },
        errorMessage: loadErrors.join(" | "),
        isInsightLoading: false,
        isLoading: false
      };
    });
  }, []);

  useEffect(() => {
    window.maintenanceDashboardReactAssetsOwned = true;
    window.maintenanceDashboardReactOperationsOwned = true;
    window.maintenanceDashboardReactPeopleOwned = true;
    window.maintenanceDashboardReactShiftOwned = true;
    window.maintenanceDashboardReactSideOwned = true;
    window.maintenanceDashboardReactTasksOwned = true;
    window.maintenanceDashboardReactTechnicalOwned = true;
    window.maintenanceDashboardReactDraftOwned = true;
    markIslandMounted(DASHBOARD_ISLAND);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    refreshDashboardData(controller.signal).catch((error: unknown) => {
      if (controller.signal.aborted) {
        return;
      }

      setDashboardState((currentState) => ({
        ...currentState,
        errorMessage: safeErrorMessage(error, "Dashboard-Daten konnten nicht geladen werden."),
        isInsightLoading: false,
        isLoading: false
      }));
    });

    return () => {
      controller.abort();
    };
  }, [refreshDashboardData]);

  useEffect(() => {
    const controller = new AbortController();

    async function refreshShiftCalendar(): Promise<void> {
      setIsShiftCalendarLoading(true);
      try {
        setShiftCalendar(employeesToShiftCalendar(dashboardState.data.employees));
      } catch (error) {
        if (!controller.signal.aborted) {
          setShiftCalendar({ entries: [], message: safeErrorMessage(error, "Schichtkalender konnte nicht geladen werden.") });
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsShiftCalendarLoading(false);
        }
      }
    }

    void refreshShiftCalendar();
    const intervalId = window.setInterval(() => {
      void refreshShiftCalendar();
    }, 60 * 1000);

    return () => {
      controller.abort();
      window.clearInterval(intervalId);
    };
  }, [dashboardState.data.employees]);

  /**
   * Open one task in the React dashboard detail modal.
   */
  async function handleOpenTask(taskId: number): Promise<void> {
    if (!taskId) return;
    setIsTaskBusy(true);
    setTaskMessage("");
    try {
      setActiveTask(await loadDashboardTask(taskId));
    } catch (error) {
      setTaskMessage(safeErrorMessage(error, "Aufgabe konnte nicht geladen werden."));
    } finally {
      setIsTaskBusy(false);
    }
  }

  /**
   * Close the React dashboard task detail modal.
   */
  function handleCloseTask(): void {
    setActiveTask(null);
    setTaskMessage("");
  }

  /**
   * Run a task mutation and refresh the dashboard state afterwards.
   */
  async function runTaskMutation(
    successMessage: string,
    mutation: () => Promise<DashboardPayload>
  ): Promise<void> {
    if (!activeTask?.id) return;
    setIsTaskBusy(true);
    setTaskMessage("");
    try {
      const result = await mutation();
      const suffix = result.generated_document ? " Wartungsbericht wurde erzeugt." : "";
      setActiveTask(await loadDashboardTask(Number(activeTask.id)));
      setTaskMessage(successMessage + suffix);
      await refreshDashboardData();
    } catch (error) {
      setTaskMessage(safeErrorMessage(error, "Aufgabe konnte nicht aktualisiert werden."));
    } finally {
      setIsTaskBusy(false);
    }
  }

  /**
   * Start the active dashboard task.
   */
  function handleStartTask(): void {
    void runTaskMutation("Aufgabe gestartet.", () => startDashboardTask(Number(activeTask?.id || 0)));
  }

  /**
   * Complete the active dashboard task.
   */
  function handleCompleteTask(payload: DashboardTaskReportPayload): void {
    void runTaskMutation("Aufgabe abgeschlossen.", () =>
      completeDashboardTask(Number(activeTask?.id || 0), payload)
    );
  }

  /**
   * Save task edits from the dashboard detail modal.
   */
  function handleUpdateTask(payload: DashboardTaskMutation): void {
    void runTaskMutation("Aufgabe aktualisiert.", () =>
      updateDashboardTask(Number(activeTask?.id || 0), payload)
    );
  }

  /**
   * Request a React-owned task draft from the existing suggestion API.
   */
  async function handleSuggestSubmit(text: string): Promise<void> {
    const trimmedText = text.trim();
    if (!trimmedText) {
      setCockpitMessage("Bitte Aufgabenbeschreibung eingeben.");
      return;
    }

    setIsDraftBusy(true);
    setCockpitMessage("KI erstellt Vorschlag...");
    try {
      const suggestion = await suggestDashboardTask(trimmedText);
      setDraftTask(taskDraftFromSuggestion(suggestion));
      setCockpitMessage("Vorschlag erstellt. Bitte prüfen und speichern.");
    } catch (error) {
      setCockpitMessage(safeErrorMessage(error, "Vorschlag konnte nicht erstellt werden."));
    } finally {
      setIsDraftBusy(false);
    }
  }

  /**
   * Persist the hidden cockpit draft through the existing task API.
   */
  async function handleDraftSubmit(payload: DashboardTaskMutation): Promise<void> {
    if (!payload.title?.trim()) {
      setCockpitMessage("Bitte Titel eingeben.");
      return;
    }

    setIsDraftBusy(true);
    setCockpitMessage("Speichert...");
    try {
      await createDashboardTask(payload);
      setDraftTask(null);
      setSuggestText("");
      setCockpitMessage("Aufgabe gespeichert.");
      await refreshDashboardData();
    } catch (error) {
      setCockpitMessage(safeErrorMessage(error, "Aufgabe konnte nicht gespeichert werden."));
    } finally {
      setIsDraftBusy(false);
    }
  }

  /**
   * Reset the hidden cockpit draft without touching loaded dashboard data.
   */
  function handleDraftCancel(): void {
    setDraftTask(null);
    setCockpitMessage("Vorschlag verworfen.");
  }

  return (
    <div data-dashboard-react-shell data-dashboard-react-runtime={dashboardState.isLoading ? "loading" : "ready"}>
      <DashboardMarkup
        activeTask={activeTask}
        dashboardState={dashboardState}
        isTaskBusy={isTaskBusy}
        isShiftCalendarLoading={isShiftCalendarLoading}
        onCloseTask={handleCloseTask}
        onCompleteTask={handleCompleteTask}
        onOpenTask={handleOpenTask}
        onStartTask={handleStartTask}
        onUpdateTask={handleUpdateTask}
        cockpitMessage={cockpitMessage}
        draftTask={draftTask}
        isDraftBusy={isDraftBusy}
        onDraftCancel={handleDraftCancel}
        onDraftChange={setDraftTask}
        onDraftSubmit={(payload) => void handleDraftSubmit(payload)}
        onSuggestSubmit={(text) => void handleSuggestSubmit(text)}
        onSuggestTextChange={setSuggestText}
        shiftCalendar={shiftCalendar}
        suggestText={suggestText}
        taskMessage={taskMessage}
      />
    </div>
  );
}
