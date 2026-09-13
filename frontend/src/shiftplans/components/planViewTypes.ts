import type {
  ShiftPlan,
  ShiftplanChangeLog,
  ShiftplanEntry,
  ShiftplanWarning,
} from "../shiftplanTypes";

export type ShiftplansPlanViewProps = {
  readonly changelog: readonly ShiftplanChangeLog[];
  readonly currentPlan: ShiftPlan | null;
  readonly isAdmin: boolean;
  readonly onDeleteEntry: (entry: ShiftplanEntry) => void;
  readonly onDeletePlan: () => void;
  readonly onDownload: () => void;
  readonly onEditEntry: (entry: ShiftplanEntry) => void;
  readonly onMoveEntryToEntry: (entryId: number, targetEntryId: number) => void;
  readonly onMoveEntryToSlot: (entryId: number, targetDate: string, targetShift: string) => void;
  readonly onPlanSelect: (index: number) => void;
  readonly onPrint: () => void;
  readonly onPublish: () => void;
  readonly plans: readonly ShiftPlan[];
  readonly selectedPlanIndex: number;
  readonly warnings: readonly ShiftplanWarning[];
  readonly writable: boolean;
};
