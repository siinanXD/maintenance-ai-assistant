import { todayIsoDate } from "../utils/date";
import { type DashboardPayload, type DashboardShiftCalendar } from "./dashboardApi";
import { peopleText } from "./dashboardPeopleModel";

/**
 * Return a local shift-calendar fallback from employee shift labels.
 */
export function employeesToShiftCalendar(employees: readonly DashboardPayload[]): DashboardShiftCalendar {
  const shifts = [
    { color: "green", end: "14:00", key: "Frueh", start: "06:00" },
    { color: "blue", end: "22:00", key: "Spaet", start: "14:00" },
    { color: "violet", end: "06:00", key: "Nacht", start: "22:00" }
  ] as const;
  const counts = employees.reduce<Map<string, number>>((currentCounts, employee) => {
    const shift = peopleText(employee, "current_shift", "Frei");
    currentCounts.set(shift, (currentCounts.get(shift) ?? 0) + 1);
    return currentCounts;
  }, new Map());

  return {
    employee: null,
    entries: shifts.map((shift) => ({
      color: shift.color,
      end_time: shift.end,
      id: null,
      machine: null,
      notes: `${String(counts.get(shift.key) || 0)} Mitarbeiter`,
      plan_id: null,
      shift: shift.key,
      start_time: shift.start,
      work_date: todayIsoDate()
    })),
    message: employees.length ? "Live aus Mitarbeiter-Schichten" : "Keine Mitarbeiterdaten für die Schichtübersicht."
  };
}

/**
 * Return a status message for the shift calendar panel.
 */
export function shiftCalendarMessage(calendar: DashboardShiftCalendar | null, isLoading: boolean): string {
  if (isLoading) return "Schichtkalender wird geladen.";
  if (calendar?.employee && typeof calendar.employee === "object") {
    return `Kalender für ${peopleText(calendar.employee, "name", "Mitarbeiter")}`;
  }

  return calendar?.message || "Schichtkalender live aktualisiert";
}
