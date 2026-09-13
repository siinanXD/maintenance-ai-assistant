import { type FormEvent, type ReactNode } from "react";

import { ActionDrawer } from "../components/ui/ActionDrawer";
import { createActionDefinition } from "../components/ui/createActionSchema";
import { HandoverDialog } from "./HandoverDialog";
import { HandoverForm } from "./HandoverForm";
import { HandoverGuidance } from "./HandoverGuidance";
import { HandoverHero } from "./HandoverHero";
import { HandoverList } from "./HandoverList";
import { HandoverStats } from "./HandoverStats";
import type {
  HandoverFilters,
  HandoverMessage,
  HandoverPayload,
  HandoverRecord,
  HandoverStats as HandoverStatsData,
  Machine,
} from "./HandoverTypes";

type HandoverMarkupProps = {
  readonly dialogMessage: HandoverMessage;
  readonly editHandover: HandoverRecord | null;
  readonly filters: HandoverFilters;
  readonly formMessage: HandoverMessage;
  readonly handovers: readonly HandoverRecord[];
  readonly loadedCount: number;
  readonly listMessage: HandoverMessage;
  readonly machines: readonly Machine[];
  readonly onCloseDialog: () => void;
  readonly onComplete: (handover: HandoverRecord) => void;
  readonly onCreateClose: () => void;
  readonly onCreateOpen: () => void;
  readonly onEdit: (handover: HandoverRecord) => void;
  readonly onFilter: () => void;
  readonly onFilterChange: (filters: HandoverFilters) => void;
  readonly onFocusList: () => void;
  readonly onResetFilters: () => void;
  readonly onSaveDialog: (id: number, payload: HandoverPayload) => void;
  readonly onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  readonly savingDialog: boolean;
  readonly showCreateDrawer: boolean;
  readonly stats: HandoverStatsData;
  readonly submitting: boolean;
  readonly writable: boolean;
};

/**
 * Render the full handover workflow with React-owned behavior.
 */
export function HandoverMarkup({
  dialogMessage,
  editHandover,
  filters,
  formMessage,
  handovers,
  loadedCount,
  listMessage,
  machines,
  onCloseDialog,
  onComplete,
  onCreateClose,
  onCreateOpen,
  onEdit,
  onFilter,
  onFilterChange,
  onFocusList,
  onResetFilters,
  onSaveDialog,
  onSubmit,
  savingDialog,
  showCreateDrawer,
  stats,
  submitting,
  writable,
}: HandoverMarkupProps): ReactNode {
  return (
    <>
      <HandoverHero onCreateOpen={onCreateOpen} onFocusList={onFocusList} writable={writable} />
      <HandoverStats stats={stats} />
      <section className="handover-workflow-grid" id="handover-workflow" aria-label="Schichtübergabe-Workflow">
        <HandoverGuidance />
      </section>
      <HandoverList
        filters={filters}
        handovers={handovers}
        loadedCount={loadedCount}
        machines={machines}
        message={listMessage}
        onComplete={onComplete}
        onEdit={onEdit}
        onFilter={onFilter}
        onFilterChange={onFilterChange}
        onResetFilters={onResetFilters}
        writable={writable}
      />
      <HandoverDialog
        handover={editHandover}
        message={dialogMessage}
        onClose={onCloseDialog}
        onSave={onSaveDialog}
        saving={savingDialog}
      />
      <ActionDrawer
        definition={createActionDefinition("handoverCreate")}
        isOpen={showCreateDrawer}
        onClose={onCreateClose}
      >
        {writable ? (
          <HandoverForm
            machines={machines}
            message={formMessage}
            onSubmit={onSubmit}
            submitting={submitting}
          />
        ) : null}
      </ActionDrawer>
    </>
  );
}
