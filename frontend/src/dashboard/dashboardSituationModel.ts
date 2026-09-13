import { type DashboardPayload, type DashboardRuntimeData } from "./dashboardApi";
import {
  activeDashboardIncidents,
  assetText,
  incidentMachineName,
  machineStatusSeverity,
  machineStatusText
} from "./dashboardAssetModel";
import { absentEmployees, peopleText, relevantVacations } from "./dashboardPeopleModel";
import {
  dashboardCriticalTasks,
  taskDepartmentName,
  taskId,
  taskIsActive,
  taskIsOverdue,
  taskPriorityLabel,
  taskRelativeDateLabel,
  taskText
} from "./dashboardTaskModel";

type DashboardFocusTone = "critical" | "good" | "muted" | "warning";

export type DashboardFocusItem = {
  readonly actionLabel: string;
  readonly detail: string;
  readonly href?: string;
  readonly id: string;
  readonly marker: string;
  readonly meta: string;
  readonly taskId?: number;
  readonly title: string;
  readonly tone: DashboardFocusTone;
};

export type DashboardSituationCard = {
  readonly actionLabel: string;
  readonly detail: string;
  readonly href?: string;
  readonly id: string;
  readonly label: string;
  readonly taskId?: number;
  readonly title: string;
  readonly tone: DashboardFocusTone;
  readonly value: string;
};

type DashboardMachineHealthCounts = {
  readonly critical: number;
  readonly good: number;
  readonly muted: number;
  readonly warning: number;
};

export type DashboardAssetSignal = {
  readonly href: string;
  readonly id: string;
  readonly meta: string;
  readonly status: string;
  readonly title: string;
  readonly tone: DashboardFocusTone;
};

/**
 * Return a stable key for flexible dashboard payloads.
 */
function dashboardPayloadKey(payload: DashboardPayload, fallback: string): string {
  return String(payload.id ?? payload.name ?? payload.title ?? fallback);
}

/**
 * Return the most useful label for an incident row.
 */
function dashboardIncidentTitle(entry: DashboardPayload): string {
  return assetText(entry, "title", assetText(entry, "error_code", "Störung"));
}

/**
 * Return a numeric count from a flexible dashboard payload.
 */
function numberValue(payload: DashboardPayload | null, key: string): number {
  const value = payload?.[key];
  const parsed = typeof value === "number" ? value : Number(value || 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * Return active dashboard tasks sorted for operational urgency.
 */
function prioritizedTasks(data: DashboardRuntimeData): readonly DashboardPayload[] {
  return data.tasks
    .filter(taskIsActive)
    .slice()
    .sort((first, second) => taskRank(first) - taskRank(second));
}

/**
 * Return a sort rank for a dashboard task.
 */
function taskRank(task: DashboardPayload): number {
  if (taskIsOverdue(task)) {
    return 0;
  }

  if (taskText(task, "priority") === "urgent") {
    return 1;
  }

  if (taskText(task, "status") === "in_progress") {
    return 2;
  }

  return 3;
}

/**
 * Convert one task into a cockpit focus item.
 */
function taskFocusItem(task: DashboardPayload): DashboardFocusItem {
  const relativeDate = taskRelativeDateLabel(task);

  return {
    actionLabel: "Aufgabe öffnen",
    detail: taskIsOverdue(task) ? "überfällig" : taskPriorityLabel(task.priority),
    id: `task-${dashboardPayloadKey(task, "task")}`,
    marker: "TASK",
    meta: [taskDepartmentName(task), relativeDate].filter(Boolean).join(" | ") || "Verantwortung klären",
    taskId: taskId(task),
    title: taskText(task, "title", "Aufgabe"),
    tone: taskIsOverdue(task) || taskText(task, "priority") === "urgent" ? "critical" : "warning"
  };
}

/**
 * Convert one incident into a cockpit focus item.
 */
function incidentFocusItem(entry: DashboardPayload): DashboardFocusItem {
  const severity = assetText(entry, "severity").toLowerCase();

  return {
    actionLabel: "Störung prüfen",
    detail: assetText(entry, "error_code", "aktiv"),
    href: "/errors",
    id: `incident-${dashboardPayloadKey(entry, "incident")}`,
    marker: "ERR",
    meta: incidentMachineName(entry),
    title: dashboardIncidentTitle(entry),
    tone: severity === "critical" || severity === "high" ? "critical" : "warning"
  };
}

/**
 * Build the highest-value focus items for the daily cockpit.
 */
export function dashboardFocusItems(data: DashboardRuntimeData): readonly DashboardFocusItem[] {
  const tasks = dashboardCriticalTasks(data).map(taskFocusItem);
  const incidents = activeDashboardIncidents(data.errors).map(incidentFocusItem);
  const fallbackTasks = prioritizedTasks(data).slice(0, 2).map(taskFocusItem);
  const items = [...tasks, ...incidents, ...fallbackTasks];
  const seen = new Set<string>();

  return items.filter((item) => {
    if (seen.has(item.id)) {
      return false;
    }

    seen.add(item.id);
    return true;
  });
}

/**
 * Return machine health counts for the cockpit.
 */
export function dashboardMachineHealthCounts(machines: readonly DashboardPayload[]): DashboardMachineHealthCounts {
  return machines.reduce<DashboardMachineHealthCounts>(
    (counts, machine) => {
      const severity = machineStatusSeverity(machine);
      return { ...counts, [severity]: counts[severity] + 1 };
    },
    { critical: 0, good: 0, muted: 0, warning: 0 }
  );
}

/**
 * Return machines sorted by operational severity.
 */
function prioritizedMachines(machines: readonly DashboardPayload[]): readonly DashboardPayload[] {
  const rank: Record<DashboardFocusTone, number> = { critical: 0, warning: 1, muted: 2, good: 3 };
  return machines.slice().sort((first, second) => {
    return rank[machineStatusSeverity(first)] - rank[machineStatusSeverity(second)];
  });
}

/**
 * Build the most important asset signals for the cockpit.
 */
export function dashboardAssetSignals(data: DashboardRuntimeData): readonly DashboardAssetSignal[] {
  const incidentSignals = activeDashboardIncidents(data.errors).map((entry) => ({
    href: "/errors",
    id: `incident-${dashboardPayloadKey(entry, "incident")}`,
    meta: [incidentMachineName(entry), assetText(entry, "error_code")].filter(Boolean).join(" | "),
    status: assetText(entry, "error_code", "Aktiv"),
    title: dashboardIncidentTitle(entry),
    tone: "warning" as const
  }));
  const machineSignals = prioritizedMachines(data.machines).map((machine) => {
    const severity = machineStatusSeverity(machine);
    return {
      href: "/machines",
      id: `machine-${dashboardPayloadKey(machine, "machine")}`,
      meta: assetText(machine, "produced_item", "Produktionsdaten offen"),
      status: machineStatusText(machine),
      title: assetText(machine, "name", "Maschine"),
      tone: severity
    };
  });

  return [...incidentSignals, ...machineSignals].slice(0, 4);
}

/**
 * Build three explanatory situation cards for the cockpit top area.
 */
export function dashboardSituationCards(data: DashboardRuntimeData): readonly DashboardSituationCard[] {
  const focusItems = dashboardFocusItems(data);
  const topFocus = focusItems[0];
  const machineCounts = dashboardMachineHealthCounts(data.machines);
  const vacations = relevantVacations(data.vacations);
  const absent = absentEmployees(data.employees);
  const shortageCount = numberValue(data.inventorySummary, "shortage_count");

  return [
    topFocus
      ? {
          actionLabel: topFocus.actionLabel,
          detail: topFocus.meta,
          href: topFocus.href,
          id: "risk",
          label: "Fokus",
          taskId: topFocus.taskId,
          title: topFocus.title,
          tone: topFocus.tone,
          value: topFocus.marker
        }
      : {
          actionLabel: "Aufgaben ansehen",
          detail: "Keine kritische Arbeit im Tagesfenster",
          href: "/tasks",
          id: "risk",
          label: "Fokus",
          title: "Tageslage stabil",
          tone: "good",
          value: "OK"
        },
    {
      actionLabel: "Maschinen ansehen",
      detail: `${machineCounts.critical} kritisch | ${machineCounts.warning} beobachten | ${machineCounts.good} stabil`,
      href: "/machines",
      id: "asset",
      label: "Anlagen",
      title: data.errors.length ? `${data.errors.length} aktive Störungen` : "Keine aktive Störung",
      tone: machineCounts.critical || data.errors.length ? "warning" : "good",
      value: machineCounts.critical ? String(machineCounts.critical) : String(data.errors.length || machineCounts.good || "--")
    },
    {
      actionLabel: vacations.length ? "Urlaub prüfen" : "Schicht prüfen",
      detail: vacations.length
        ? `${vacations.length} offene Anträge`
        : absent.length
          ? absent.slice(0, 2).map((employee) => peopleText(employee, "name", "Abwesend")).join(", ")
          : shortageCount
            ? `${shortageCount} Materialengpässe`
            : `${data.employees.length || "--"} Mitarbeitende im Blick`,
      href: vacations.length ? "/vacations" : absent.length ? "/employees" : shortageCount ? "/inventory" : "/handover",
      id: "people",
      label: "Entscheidung",
      title: vacations.length
        ? "Urlaubsfreigabe offen"
        : absent.length
          ? `${absent.length} abwesend markiert`
          : shortageCount
            ? "Material klären"
            : "Schichtlage ohne Warnung",
      tone: vacations.length || absent.length || shortageCount ? "warning" : "good",
      value: vacations.length || absent.length || shortageCount ? "!" : "OK"
    }
  ];
}
