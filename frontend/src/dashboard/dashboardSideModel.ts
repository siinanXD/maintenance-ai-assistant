import { type DashboardPayload, type DashboardRuntimeData } from "./dashboardApi";
import { assetText } from "./dashboardAssetModel";
type BriefingItem = {
  readonly href?: string;
  readonly icon: string;
  readonly meta: string;
  readonly title: string;
  readonly variant: string;
};

/**
 * Return a list payload from an object field.
 */
function arrayValue(payload: DashboardPayload | null | undefined, key: string): readonly DashboardPayload[] {
  const value = payload?.[key];
  return Array.isArray(value) ? (value as DashboardPayload[]) : [];
}

/**
 * Return a dashboard briefing section list.
 */
function briefingSections(data: DashboardRuntimeData): readonly DashboardPayload[] {
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

