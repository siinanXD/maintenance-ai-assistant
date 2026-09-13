import type { ReactNode } from "react";

import { PageActionBar } from "../../components/ui/PageActionBar";
import { createActionDefinition } from "../../components/ui/createActionSchema";

type TaskHeaderProps = {
  readonly writable: boolean;
  readonly onCreateFromMessage: () => void;
  readonly onCreateTask: () => void;
  readonly onRefreshPriorities: () => Promise<void>;
  readonly priorityBusy: boolean;
};

/**
 * Render the task page hero and command actions.
 */
export function TaskHeader({
  writable,
  onCreateFromMessage,
  onCreateTask,
  onRefreshPriorities,
  priorityBusy
}: TaskHeaderProps): ReactNode {
  return (
    <section className="page-hero task-workboard-hero is-compact">
      <div>
        <h1 className="page-title">Aufgaben</h1>
        <p className="page-description">
          Aufträge aus Störungen, Wartung und Prüfungen – nach Status und Fälligkeit.
        </p>
      </div>
      <PageActionBar
        label="Aufgaben Aktionen"
        actions={[
          { hidden: !writable, onClick: onCreateTask, schema: createActionDefinition("taskCreate"), variant: "primary" },
          { hidden: !writable, onClick: onCreateFromMessage, schema: createActionDefinition("taskSuggestion"), variant: "outline" },
          {
            disabled: priorityBusy,
            label: priorityBusy ? "Wird geladen..." : "Priorität aktualisieren",
            onClick: () => void onRefreshPriorities(),
            variant: "outline"
          }
        ]}
      />
    </section>
  );
}
