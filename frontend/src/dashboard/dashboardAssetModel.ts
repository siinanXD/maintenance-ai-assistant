import { type DashboardPayload } from "./dashboardApi";

type DashboardSignal = "critical" | "good" | "muted" | "warning";

/**
 * Return a normalized text field from a dashboard payload.
 */
export function assetText(payload: DashboardPayload | null | undefined, key: string, fallback = ""): string {
  const value = payload?.[key];
  return typeof value === "string" && value.trim() ? value : fallback;
}

/**
 * Return a nested machine name from an incident payload.
 */
export function incidentMachineName(entry: DashboardPayload): string {
  const machine = entry.machine_obj;
  if (typeof machine === "object" && machine !== null && !Array.isArray(machine)) {
    const name = (machine as Record<string, unknown>).name;
    if (typeof name === "string" && name.trim()) {
      return name;
    }
  }

  return assetText(entry, "machine", "-");
}

/**
 * Return active dashboard incidents sorted by severity and recency.
 */
export function activeDashboardIncidents(errors: readonly DashboardPayload[]): readonly DashboardPayload[] {
  const severityRank: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };

  return errors
    .filter((entry) => assetText(entry, "status").toLowerCase() !== "closed")
    .slice()
    .sort((first, second) => {
      const firstRank = severityRank[assetText(first, "severity").toLowerCase()] ?? 4;
      const secondRank = severityRank[assetText(second, "severity").toLowerCase()] ?? 4;
      if (firstRank !== secondRank) return firstRank - secondRank;
      return assetText(second, "last_seen_at", assetText(second, "created_at")).localeCompare(
        assetText(first, "last_seen_at", assetText(first, "created_at"))
      );
    });
}

/**
 * Return a dashboard severity class from a signal name.
 */
export function dashboardSignalClass(signal: DashboardSignal): string {
  if (signal === "critical") return "is-critical";
  if (signal === "warning") return "is-warning";
  if (signal === "good") return "is-good";
  return "is-muted";
}

/**
 * Return a machine severity from its status text.
 */
export function machineStatusSeverity(machine: DashboardPayload): DashboardSignal {
  const status = assetText(machine, "status").toLowerCase();
  if (status.includes("down") || status.includes("stör") || status.includes("stoer") || status.includes("error")) {
    return "critical";
  }

  if (status.includes("wart") || status.includes("maintenance") || status.includes("pause") || status.includes("prüf")) {
    return "warning";
  }

  if (status.includes("run") || status.includes("aktiv") || status.includes("ok") || status.includes("bereit")) {
    return "good";
  }

  return "muted";
}

/**
 * Return a localized machine status label.
 */
export function machineStatusText(machine: DashboardPayload): string {
  const status = assetText(machine, "status", "unbekannt");
  if (status === "running") return "Läuft";
  if (status === "down") return "Stillstand";
  if (status === "maintenance") return "Wartung";
  return status;
}

