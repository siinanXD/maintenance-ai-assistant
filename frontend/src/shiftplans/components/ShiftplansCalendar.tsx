import { type DragEvent, type ReactNode } from "react";

import type {
  ShiftPlan,
  ShiftplanCalendarSlot,
  ShiftplanEntry,
} from "../shiftplanTypes";
import type { ShiftplansPlanViewProps } from "./planViewTypes";
import {
  DAYS_DE,
  SHIFT_LABEL,
  activePlanShifts,
  calendarIndex,
  isUnassignedSlot,
  localIsoDate,
  planDates,
  slotEmployeeName,
  slotMachineName,
} from "../shiftplanUtils";

/**
 * Return one rendered shiftplan chip.
 */
function ShiftplanChip({
  canEdit,
  entry,
  onDeleteEntry,
  onEditEntry,
  onMoveEntryToEntry,
}: {
  readonly canEdit: boolean;
  readonly entry: ShiftplanCalendarSlot;
  readonly onDeleteEntry: (entry: ShiftplanEntry) => void;
  readonly onEditEntry: (entry: ShiftplanEntry) => void;
  readonly onMoveEntryToEntry: (entryId: number, targetEntryId: number) => void;
}): ReactNode {
  const machineName = slotMachineName(entry);
  const employeeName = slotEmployeeName(entry);
  const className = `sp-chip${isUnassignedSlot(entry) ? " sp-unassigned" : ""}`;
  const body = (
    <>
      {machineName ? <span className="sp-machine">{machineName}</span> : null}
      <span className="sp-emp">{employeeName}</span>
    </>
  );

  if (!canEdit || isUnassignedSlot(entry)) {
    return <div className={className}>{body}</div>;
  }
  const editableEntry = entry as ShiftplanEntry;

  /**
   * Move a dragged entry onto this existing entry.
   */
  function handleDrop(event: DragEvent<HTMLButtonElement>): void {
    event.preventDefault();
    event.stopPropagation();
    const draggedEntryId = Number.parseInt(event.dataTransfer.getData("entry_id"), 10);
    if (Number.isInteger(draggedEntryId) && draggedEntryId !== editableEntry.id) {
      onMoveEntryToEntry(draggedEntryId, editableEntry.id);
    }
  }

  return (
    <button
      aria-label={`Bearbeiten: ${employeeName}`}
      className={className}
      draggable
      type="button"
      onClick={() => onEditEntry(editableEntry)}
      onContextMenu={(event) => {
        event.preventDefault();
        onDeleteEntry(editableEntry);
      }}
      onDragStart={(event) => {
        event.dataTransfer.setData("entry_id", String(editableEntry.id));
        event.dataTransfer.effectAllowed = "move";
      }}
      onDragOver={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
      onDrop={handleDrop}
    >
      {body}
    </button>
  );
}

/**
 * Render the calendar grid for the current plan.
 */
export function ShiftplansCalendar({
  currentPlan,
  onDeleteEntry,
  onEditEntry,
  onMoveEntryToEntry,
  onMoveEntryToSlot,
  writable,
}: Pick<ShiftplansPlanViewProps, "currentPlan" | "onDeleteEntry" | "onEditEntry" | "onMoveEntryToEntry" | "onMoveEntryToSlot" | "writable">): ReactNode {
  const dates = currentPlan ? planDates(currentPlan) : [];
  const entriesByShift = currentPlan ? calendarIndex(currentPlan) : new Map<string, Map<string, ShiftplanCalendarSlot[]>>();
  const activeShifts = currentPlan ? activePlanShifts(currentPlan) : [];
  const canEdit = Boolean(writable && currentPlan && !currentPlan.is_preview);

  return (
    <div id="sp-table-wrap" hidden={!currentPlan}>
      <ShiftplansPrintHeader currentPlan={currentPlan} />
      <div className="overflow-x-auto">
        <table id="sp-grid" className="sp-excel-table">
          <caption>Schichtplan-Kalender mit Mitarbeitern, Tagen und Schichten</caption>
          <thead id="sp-thead">
            <tr>
              <th className="sp-col-shift" scope="col">Schicht</th>
              {dates.map((date) => (
                <th className="sp-col-day" key={localIsoDate(date)} scope="col">
                  <span className="sp-dow">{DAYS_DE[date.getDay()]}</span>
                  <br />
                  <span className="sp-date">{String(date.getDate()).padStart(2, "0")}.{String(date.getMonth() + 1).padStart(2, "0")}.</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody id="sp-tbody">
            {!activeShifts.length ? (
              <tr>
                <td className="text-center" colSpan={dates.length + 1} style={{ opacity: 0.5 }}>
                  Keine Einträge im Plan.
                </td>
              </tr>
            ) : activeShifts.map((shiftKey) => (
              <tr key={shiftKey}>
                <th className={`sp-col-shift sp-shift-label sp-shift-${String(shiftKey).toLowerCase()}`} scope="row">
                  {SHIFT_LABEL[String(shiftKey)] || shiftKey}
                </th>
                {dates.map((date) => {
                  const dateString = localIsoDate(date);
                  const dayEntries = entriesByShift.get(String(shiftKey))?.get(dateString) || [];
                  return (
                    <td
                      className={`sp-day-cell sp-cell-${String(shiftKey).toLowerCase()}`}
                      key={`${shiftKey}-${dateString}`}
                      onDragOver={(event) => {
                        if (canEdit) event.preventDefault();
                      }}
                      onDrop={(event) => {
                        if (!canEdit) return;
                        event.preventDefault();
                        const draggedEntryId = Number.parseInt(event.dataTransfer.getData("entry_id"), 10);
                        if (Number.isInteger(draggedEntryId)) onMoveEntryToSlot(draggedEntryId, dateString, String(shiftKey));
                      }}
                    >
                      {dayEntries.length ? dayEntries.map((entry) => (
                        <ShiftplanChip
                          canEdit={canEdit}
                          entry={entry}
                          key={isUnassignedSlot(entry) ? `${entry.shift}-${entry.work_date}-${slotMachineName(entry)}` : entry.id}
                          onDeleteEntry={onDeleteEntry}
                          onEditEntry={onEditEntry}
                          onMoveEntryToEntry={onMoveEntryToEntry}
                        />
                      )) : <span className="sp-empty">-</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ShiftplansCalendarLegend />
    </div>
  );
}

/**
 * Render the printable plan metadata row.
 */
function ShiftplansPrintHeader({ currentPlan }: { readonly currentPlan: ShiftPlan | null }): ReactNode {
  return (
    <div className="print-only" style={{ marginBottom: "12px" }}>
      <strong id="print-title" style={{ fontSize: "14pt" }}>
        {currentPlan?.title || "Schichtplan"}
      </strong>
      <span id="print-meta" style={{ marginLeft: "16px", fontSize: "10pt", color: "#555" }}>
        {currentPlan ? `Abteilung: ${currentPlan.department || "-"} | ${currentPlan.start_date} | ${currentPlan.days} Tage${currentPlan.status === "published" ? " | Veröffentlicht" : " | Entwurf"}` : ""}
      </span>
    </div>
  );
}

/**
 * Render the visible shift legend below the calendar.
 */
function ShiftplansCalendarLegend(): ReactNode {
  return (
    <div className="toolbar mt-3 no-print" style={{ gap: "12px", flexWrap: "wrap" }}>
      <span className="badge badge-success badge-outline">F = Frühschicht 06-14</span>
      <span className="badge badge-info badge-outline">S = Spätschicht 14-22</span>
      <span className="badge badge-secondary badge-outline">N = Nachtschicht 22-06</span>
      <span className="badge badge-warning badge-outline">U = Urlaub</span>
      <span className="badge badge-ghost badge-outline">- = Frei</span>
    </div>
  );
}
