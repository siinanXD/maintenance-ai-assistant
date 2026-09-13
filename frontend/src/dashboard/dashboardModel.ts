import { todayIsoDate } from "../utils/date";
import { type DashboardPayload, type DashboardRuntimeData, EMPTY_DASHBOARD_DATA } from "./dashboardApi";

export type DashboardViewState = {
  readonly data: DashboardRuntimeData;
  readonly errorMessage: string;
  /** Operational data (tasks, incidents, machines, people) is still loading. */
  readonly isLoading: boolean;
  /** AI insights (briefing, AI and knowledge status) are still loading. */
  readonly isInsightLoading: boolean;
};

export type DashboardKpiState = {
  readonly colorClass: string;
  readonly label: string;
  readonly meta: string;
  readonly progressWidth: string;
  readonly value: string;
};

export const EMPTY_DASHBOARD_VIEW_STATE: DashboardViewState = {
  data: EMPTY_DASHBOARD_DATA,
  errorMessage: "",
  isInsightLoading: true,
  isLoading: true
};

/**
 * Return a string field from a flexible dashboard payload.
 */
function textValue(payload: DashboardPayload, key: string): string {
  const value = payload[key];
  return typeof value === "string" ? value : "";
}

/**
 * Return true when a dashboard task is not closed.
 */
function isActiveTask(task: DashboardPayload): boolean {
  const status = textValue(task, "status");
  return status !== "done" && status !== "cancelled";
}

/**
 * Return true when a task due date is earlier than today.
 */
function isOverdueTask(task: DashboardPayload): boolean {
  const dueDate = textValue(task, "due_date");
  return Boolean(dueDate && dueDate < todayIsoDate() && isActiveTask(task));
}

/**
 * Return a capped KPI progress percentage.
 */
function progressPercent(value: number, total: number): string {
  if (total <= 0) {
    return "0%";
  }

  return `${Math.min(100, Math.max(0, Math.round((value / total) * 100)))}%`;
}

/**
 * Return a compact machine-status KPI value.
 */
function machineStatusValue(machines: readonly DashboardPayload[]): string {
  if (!machines.length) {
    return "--";
  }

  const activeMachines = machines.filter((machine) => {
    const status = textValue(machine, "status").toLowerCase();
    return status !== "offline" && status !== "störung" && status !== "stoerung";
  });

  return `${activeMachines.length}/${machines.length}`;
}

/**
 * Build the four cockpit KPI cards from the loaded dashboard data.
 */
export function dashboardKpiCards(state: DashboardViewState): readonly DashboardKpiState[] {
  const { data } = state;
  const activeTasks = data.tasks.filter(isActiveTask);
  const openTasks = activeTasks.filter((task) => textValue(task, "status") === "open");
  const progressTasks = activeTasks.filter((task) => textValue(task, "status") === "in_progress");
  const criticalTasks = activeTasks.filter(
    (task) => textValue(task, "priority") === "urgent" || isOverdueTask(task)
  );

  return [
    {
      colorClass: "is-red",
      label: "Kritisch heute",
      meta: criticalTasks.length ? "sofort prüfen" : "keine kritische Arbeit",
      progressWidth: progressPercent(criticalTasks.length, Math.max(activeTasks.length, 1)),
      value: String(criticalTasks.length)
    },
    {
      colorClass: "is-orange",
      label: "Aktive Störungen",
      meta: data.errors.length ? `${data.errors.length} aktive Störungen` : "keine aktive Störung",
      progressWidth: progressPercent(data.errors.length, Math.max(data.machines.length, 1)),
      value: data.errors.length ? String(data.errors.length) : "--"
    },
    {
      colorClass: "is-blue",
      label: "Offene Aufgaben",
      meta: `${progressTasks.length} in Arbeit`,
      progressWidth: progressPercent(openTasks.length, Math.max(data.tasks.length, 1)),
      value: String(openTasks.length)
    },
    {
      colorClass: "is-teal",
      label: "Maschinenstatus",
      meta: data.machines.length ? `${data.machines.length} Maschinen im Blick` : "Maschinen werden geladen",
      progressWidth: progressPercent(data.machines.length - data.errors.length, Math.max(data.machines.length, 1)),
      value: machineStatusValue(data.machines)
    }
  ];
}
