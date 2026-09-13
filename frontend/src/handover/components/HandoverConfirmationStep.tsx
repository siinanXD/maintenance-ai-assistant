import { type ReactNode } from "react";

import type { HandoverMessage } from "../handoverTypes";

/**
 * Render the submit confirmation area.
 */
export function ConfirmationStep({
  message,
  submitting,
}: {
  readonly message: HandoverMessage;
  readonly submitting: boolean;
}): ReactNode {
  return (
    <section className="handover-confirmation">
      <label className="handover-checkbox" htmlFor="ho-confirmed">
        <input id="ho-confirmed" name="confirmed" type="checkbox" />
        <span>
          <strong>Übergabe direkt bestätigen</strong>
          <small>
            Wenn aktiviert, wird das Protokoll sofort abgeschlossen und kann danach nicht mehr bearbeitet werden.
          </small>
        </span>
      </label>
      <div className="toolbar form-actions">
        <button className="btn btn-primary" id="ho-submit-btn" type="submit" disabled={submitting}>
          {submitting ? "Speichert..." : "Übergabe speichern"}
        </button>
        <span className={`panel-meta${message.isError ? " is-error" : ""}`} id="ho-msg" role="status" aria-live="polite">
          {message.text}
        </span>
      </div>
    </section>
  );
}
