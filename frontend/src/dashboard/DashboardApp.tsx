import { useCallback, useEffect, useState, type ReactNode } from "react";

import { safeErrorMessage } from "../utils/errors";
import {
  completeDashboardTask,
  loadDashboardCoreData,
  loadDashboardInsightData,
  loadDashboardTask,
  startDashboardTask,
  updateDashboardTask,
  type DashboardPayload,
  type DashboardShiftCalendar,
  type DashboardTaskMutation,
  type DashboardTaskReportPayload
} from "./dashboardApi";
import { DashboardCockpitPanels } from "./components/DashboardCockpitPanels";
import { DashboardHero } from "./components/DashboardHero";
import { DashboardKpis } from "./components/DashboardKpis";
import { dashboardKpiCards, EMPTY_DASHBOARD_VIEW_STATE, type DashboardViewState } from "./dashboardModel";
import { employeesToShiftCalendar } from "./dashboardShiftModel";
import { DashboardSituationStrip } from "./components/DashboardSituationStrip";
import { DashboardTaskDetailModal } from "./components/DashboardTaskDetailModal";
import { DashboardTechnicalDetails } from "./components/DashboardTechnicalDetails";

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

  return (
    <>
      <DashboardHero dashboardState={dashboardState} />
      <DashboardSituationStrip dashboardState={dashboardState} onOpenTask={handleOpenTask} />
      <DashboardKpis kpis={dashboardKpiCards(dashboardState)} />
      <DashboardCockpitPanels
        dashboardState={dashboardState}
        isShiftCalendarLoading={isShiftCalendarLoading}
        onOpenTask={handleOpenTask}
        shiftCalendar={shiftCalendar}
      />
      <DashboardTechnicalDetails dashboardState={dashboardState} />
      <DashboardTaskDetailModal
        activeTask={activeTask}
        isBusy={isTaskBusy}
        message={taskMessage}
        onClose={handleCloseTask}
        onComplete={handleCompleteTask}
        onStart={handleStartTask}
        onUpdate={handleUpdateTask}
      />
    </>
  );
}
