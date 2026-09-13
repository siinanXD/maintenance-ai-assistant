import { todayIsoDate } from "../utils/date";
import { type DashboardPayload, type DashboardRuntimeData, EMPTY_DASHBOARD_DATA } from "./dashboardApi";
import {
  handoverStatusMeta,
  handoverStatusValue,
  peopleStatusMeta,
  peopleStatusValue,
  relevantVacations
} from "./dashboardPeopleModel";

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
  readonly metaHook?: string;
  readonly progressHook: string;
  readonly progressWidth: string;
  readonly value: string;
  readonly valueHook: string;
};

export type DashboardStatusChipState = {
  readonly colorClass: string;
  readonly label: string;
  readonly meta: string;
  readonly metaHook?: string;
  readonly value: string;
  readonly valueHook: string;
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
 * Return a numeric field from a flexible dashboard payload.
 */
function numberValue(payload: DashboardPayload | null, key: string): number {
  const value = payload?.[key];
  const parsed = typeof value === "number" ? value : Number(value || 0);
  return Number.isFinite(parsed) ? parsed : 0;
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
 * Return a compact system health value from AI and knowledge status payloads.
 */
function systemStatusValue(data: DashboardRuntimeData): string {
  if (data.loadErrors.length) {
    return "Prüfen";
  }

  const status = textValue(data.aiStatus ?? {}, "status").toLowerCase();
  if (status && status !== "ok" && status !== "ready" && status !== "healthy") {
    return "Prüfen";
  }

  return data.aiStatus || data.knowledgeStatus || data.retrievalTelemetry ? "OK" : "--";
}

/**
 * Build dashboard KPI cards from React-owned dashboard data.
 */
export function dashboardKpiCards(state: DashboardViewState): readonly DashboardKpiState[] {
  const { data } = state;
  const activeTasks = data.tasks.filter(isActiveTask);
  const openTasks = activeTasks.filter((task) => textValue(task, "status") === "open");
  const progressTasks = activeTasks.filter((task) => textValue(task, "status") === "in_progress");
  const doneTasks = data.tasks.filter((task) => textValue(task, "status") === "done");
  const criticalTasks = activeTasks.filter(
    (task) => textValue(task, "priority") === "urgent" || isOverdueTask(task)
  );
  const vacationCount = relevantVacations(data.vacations).length;
  const shortageCount = numberValue(data.inventorySummary, "shortage_count");
  const knowledgeGapCount = data.knowledgeGaps.length || numberValue(data.knowledgeStatus, "open_gap_count");

  return [
    {
      colorClass: "is-red",
      label: "Kritisch heute",
      meta: criticalTasks.length ? "sofort prüfen" : "keine kritische Arbeit",
      metaHook: "data-dashboard-critical-meta",
      progressHook: "data-dashboard-critical-progress",
      progressWidth: progressPercent(criticalTasks.length, Math.max(activeTasks.length, 1)),
      value: String(criticalTasks.length),
      valueHook: "data-dashboard-critical-count"
    },
    {
      colorClass: "is-orange",
      label: "Aktive Störungen",
      meta: data.errors.length ? `${data.errors.length} aktive Störungen` : "keine aktive Störung",
      metaHook: "data-dashboard-machine-status-meta",
      progressHook: "data-dashboard-error-progress",
      progressWidth: progressPercent(data.errors.length, Math.max(data.machines.length, 1)),
      value: data.errors.length ? String(data.errors.length) : "--",
      valueHook: "data-dashboard-unresolved-errors"
    },
    {
      colorClass: "is-blue",
      label: "Offene Aufgaben",
      meta: `${progressTasks.length} in Arbeit`,
      metaHook: "data-dashboard-open-meta",
      progressHook: "data-dashboard-open-progress",
      progressWidth: progressPercent(openTasks.length, Math.max(data.tasks.length, 1)),
      value: String(openTasks.length),
      valueHook: "data-dashboard-open-count"
    },
    {
      colorClass: "is-teal",
      label: "Maschinenstatus",
      meta: data.machines.length ? `${data.machines.length} Maschinen im Blick` : "Maschinen werden geladen",
      metaHook: "data-dashboard-machine-kpi-meta",
      progressHook: "data-dashboard-machine-progress",
      progressWidth: progressPercent(data.machines.length - data.errors.length, Math.max(data.machines.length, 1)),
      value: machineStatusValue(data.machines),
      valueHook: "data-dashboard-machine-status"
    },
    {
      colorClass: "is-green",
      label: "Erledigte Aufgaben",
      meta: "Abgeschlossen im aktuellen Fenster",
      progressHook: "data-dashboard-done-progress",
      progressWidth: progressPercent(doneTasks.length, Math.max(data.tasks.length, 1)),
      value: String(doneTasks.length),
      valueHook: "data-dashboard-done-count"
    },
    {
      colorClass: "is-cyan",
      label: "Schichtlage",
      meta: handoverStatusMeta(data),
      metaHook: "data-dashboard-shift-meta",
      progressHook: "data-dashboard-shift-progress",
      progressWidth: data.handovers.length ? "72%" : "18%",
      value: handoverStatusValue(data),
      valueHook: "data-dashboard-shift-status"
    },
    {
      colorClass: "is-indigo",
      label: "Personalhinweise",
      meta: peopleStatusMeta(data),
      metaHook: "data-dashboard-people-meta",
      progressHook: "data-dashboard-people-progress",
      progressWidth: progressPercent(data.employees.length - vacationCount, Math.max(data.employees.length, 1)),
      value: peopleStatusValue(data),
      valueHook: "data-dashboard-people-status"
    },
    {
      colorClass: "is-slate",
      label: "Systemstatus",
      meta: knowledgeGapCount || shortageCount ? `${knowledgeGapCount + shortageCount} Hinweise` : "Indexstatus stabil",
      metaHook: "data-dashboard-index-status-meta",
      progressHook: "data-dashboard-system-progress",
      progressWidth: data.loadErrors.length ? "35%" : "100%",
      value: systemStatusValue(data),
      valueHook: "data-dashboard-system-status"
    }
  ];
}

/**
 * Build the four operational KPI cards for the first viewport cockpit.
 */
export function dashboardPrimaryKpiCards(state: DashboardViewState): readonly DashboardKpiState[] {
  return dashboardKpiCards(state).slice(0, 4);
}

/**
 * Build compact status chips for secondary dashboard signals.
 */
export function dashboardStatusChips(state: DashboardViewState): readonly DashboardStatusChipState[] {
  return dashboardKpiCards(state).slice(4).map((kpi) => ({
    colorClass: kpi.colorClass,
    label: kpi.label,
    meta: kpi.meta,
    metaHook: kpi.metaHook,
    value: kpi.value,
    valueHook: kpi.valueHook
  }));
}

/**
 * Return a compact dashboard load-status message for hidden status hooks.
 */
export function dashboardLoadMessage(state: DashboardViewState): string {
  if (state.errorMessage) {
    return state.errorMessage;
  }

  if (state.isLoading) {
    return "Dashboard-Daten werden geladen.";
  }

  return "Dashboard-Daten geladen.";
}
