import { type DashboardPayload, type DashboardRuntimeData } from "./dashboardApi";
import { assetText, incidentMachineName } from "./dashboardAssetModel";
import { taskIsOverdue, taskPriorityLabel, taskText } from "./dashboardTaskModel";

export type BriefingItem = {
  readonly href?: string;
  readonly icon: string;
  readonly meta: string;
  readonly title: string;
  readonly variant: string;
};

export type InventoryMetric = {
  readonly detail: string;
  readonly label: string;
  readonly value: string;
};

/**
 * Return a nested object payload.
 */
function objectValue(payload: DashboardPayload | null | undefined, key: string): DashboardPayload {
  const value = payload?.[key];
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as DashboardPayload)
    : {};
}

/**
 * Return a list payload from an object field.
 */
function arrayValue(payload: DashboardPayload | null | undefined, key: string): readonly DashboardPayload[] {
  const value = payload?.[key];
  return Array.isArray(value) ? (value as DashboardPayload[]) : [];
}

/**
 * Return a numeric payload field.
 */
function numberValue(payload: DashboardPayload | null | undefined, key: string): number {
  const value = payload?.[key];
  const parsed = typeof value === "number" ? value : Number(value || 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * Return a dashboard briefing section list.
 */
export function briefingSections(data: DashboardRuntimeData): readonly DashboardPayload[] {
  return arrayValue(data.dailyBriefing, "sections");
}

/**
 * Return a compact briefing summary.
 */
export function briefingSummary(data: DashboardRuntimeData, isLoading = true): string {
  return assetText(
    data.dailyBriefing ?? {},
    "summary",
    isLoading ? "Kurzlage wird erstellt." : "Kurzlage ist gerade nicht verfügbar."
  );
}

/**
 * Return visual class for one briefing item.
 */
function briefingVariant(severity: unknown): string {
  const value = String(severity || "").toLowerCase();
  if (value === "critical" || value === "urgent") return "is-critical";
  if (value === "warning" || value === "soon" || value === "high") return "is-warning";
  return "is-success";
}

/**
 * Build flattened briefing items for the dashboard side panel.
 */
export function briefingItems(data: DashboardRuntimeData): readonly BriefingItem[] {
  return briefingSections(data).flatMap((section) => {
    const sectionItems = arrayValue(section, "items").slice(0, 2);
    if (!sectionItems.length) {
      return [{
        icon: String(section.type || "AI").toUpperCase().slice(0, 2),
        meta: `${String(section.count || 0)} Hinweise`,
        title: assetText(section, "title", "Briefing"),
        variant: "is-success"
      }];
    }

    return sectionItems.map((item) => ({
      href: assetText(item, "url"),
      icon: String(section.type || "AI").toUpperCase().slice(0, 2),
      meta: assetText(item, "summary", assetText(item, "severity")),
      title: assetText(item, "title", "Hinweis"),
      variant: briefingVariant(item.severity)
    }));
  });
}

/**
 * Build activity-feed items from dashboard state.
 */
export function activityItems(data: DashboardRuntimeData): readonly BriefingItem[] {
  const items: BriefingItem[] = [];

  data.tasks.slice(0, 3).forEach((task) => {
    items.push({
      href: "/tasks",
      icon: "TA",
      meta: `${taskPriorityLabel(task.priority)} · ${taskText(task, "status", "offen")}`,
      title: taskText(task, "title", "Aufgabe"),
      variant: taskText(task, "priority") === "urgent" || taskIsOverdue(task) ? "is-warning" : "is-muted"
    });
  });

  data.errors.slice(0, 3).forEach((entry) => {
    items.push({
      href: "/errors",
      icon: "FE",
      meta: incidentMachineName(entry),
      title: assetText(entry, "title", assetText(entry, "error_code", "Störung")),
      variant: "is-warning"
    });
  });

  briefingSections(data).slice(0, 2).forEach((section) => {
    items.push({
      href: "#daily-briefing",
      icon: "AI",
      meta: `${String(section.count || 0)} Hinweise`,
      title: assetText(section, "title", "Briefing"),
      variant: "is-muted"
    });
  });

  return items.slice(0, 8);
}

/**
 * Return inventory counts from the dashboard summary.
 */
function inventoryCounts(summary: DashboardPayload | null): { readonly critical: number; readonly low: number; readonly ok: number } {
  const counts = objectValue(summary, "status_counts");
  return {
    critical: numberValue(counts, "critical"),
    low: numberValue(counts, "low"),
    ok: numberValue(counts, "ok")
  };
}

/**
 * Return inventory metrics for the dashboard side panel.
 */
export function inventoryMetrics(data: DashboardRuntimeData): readonly InventoryMetric[] {
  const counts = inventoryCounts(data.inventorySummary);
  return [
    { detail: "Artikel", label: "Kritisch", value: String(counts.critical) },
    { detail: "Artikel", label: "Niedrig", value: String(counts.low) },
    { detail: "Artikel", label: "OK", value: String(counts.ok) },
    {
      detail: "Lagerwert",
      label: "Gesamtwert",
      value: new Intl.NumberFormat("de-DE", { currency: "EUR", style: "currency" }).format(
        numberValue(data.inventorySummary, "total_value")
      )
    }
  ];
}

/**
 * Return top inventory shortages.
 */
export function inventoryShortages(data: DashboardRuntimeData): readonly DashboardPayload[] {
  return arrayValue(data.inventorySummary, "top_shortages").slice(0, 3);
}
