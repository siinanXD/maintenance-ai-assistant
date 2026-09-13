import { type FormEvent, type ReactNode } from "react";

import { ConfirmationStep } from "./HandoverConfirmationStep";
import {
  AssignmentStep,
  FollowUpStep,
  ProblemStep,
  ShiftStep,
  StatusStep,
} from "./HandoverFormSteps";
import type { HandoverMessage, Machine } from "../handoverTypes";

type HandoverFormProps = {
  readonly machines: readonly Machine[];
  readonly message: HandoverMessage;
  readonly onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  readonly submitting: boolean;
};

/**
 * Render the full handover capture form.
 */
export function HandoverForm({ machines, message, onSubmit, submitting }: HandoverFormProps): ReactNode {
  return (
    <article className="handover-workflow-panel app-card">
      <header className="handover-panel-header">
        <div>
          <h2>Neue Übergabe erfassen</h2>
          <p>Schicht, Maschine, Status, Probleme und offene Punkte in einem Ablauf dokumentieren.</p>
        </div>
      </header>
      <form className="handover-form" id="ho-form" onSubmit={onSubmit}>
        <ShiftStep />
        <AssignmentStep machines={machines} />
        <StatusStep />
        <ProblemStep />
        <FollowUpStep />
        <ConfirmationStep message={message} submitting={submitting} />
      </form>
    </article>
  );
}
