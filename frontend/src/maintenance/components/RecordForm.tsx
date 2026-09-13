import { useState, type FormEvent, type ReactNode } from "react";

import { RESULT_LABELS, todayIso } from "../maintenanceLabels";
import { saveRecord } from "../maintenanceApi";
import type { MaintenancePlan, RecordDraft, RecordResult } from "../maintenanceTypes";

type RecordFormProps = {
  readonly plan: MaintenancePlan;
  readonly onSaved: (message: string) => Promise<void>;
};

/**
 * Document an executed maintenance or inspection with its result.
 */
export function RecordForm({ plan, onSaved }: RecordFormProps): ReactNode {
  const [draft, setDraft] = useState<RecordDraft>({
    performed_on: todayIso(),
    performed_by: "",
    result: "passed",
    notes: "",
    create_follow_up: true
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const noun = plan.kind === "inspection" ? "Prüfung" : "Wartung";

  /**
   * Store the record and report what happens next.
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { record, plan: updated } = await saveRecord(plan.id, draft);
      const followUp = record.follow_up_task_id ? " Aufgabe zur Mängelbeseitigung angelegt." : "";
      await onSaved(`${noun} dokumentiert. Nächste Fälligkeit ${updated.next_due_date.split("-").reverse().join(".")}.${followUp}`);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Nachweis konnte nicht gespeichert werden.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="plan-form" onSubmit={(event) => void handleSubmit(event)}>
      <p className="plan-form-context">
        <strong>{plan.title}</strong>
        <span>{[plan.machine?.name, plan.legal_basis].filter(Boolean).join(" · ") || "Ohne Maschine"}</span>
      </p>
      <div className="plan-form-row">
        <label className="field">
          <span>Durchgeführt am</span>
          <input className="input input-bordered" max={todayIso()} required type="date" value={draft.performed_on} onChange={(event) => setDraft({ ...draft, performed_on: event.currentTarget.value })} />
        </label>
        <label className="field">
          <span>Durchgeführt von</span>
          <input className="input input-bordered" maxLength={120} placeholder="Name oder Prüffirma" required value={draft.performed_by} onChange={(event) => setDraft({ ...draft, performed_by: event.currentTarget.value })} />
        </label>
      </div>
      <fieldset className="plan-kind-toggle is-result">
        <legend>Ergebnis</legend>
        {(Object.keys(RESULT_LABELS) as RecordResult[]).map((result) => (
          <label className={`is-${result}`} key={result}>
            <input checked={draft.result === result} name="result" type="radio" value={result} onChange={() => setDraft({ ...draft, result })} />
            <span>{RESULT_LABELS[result]}</span>
          </label>
        ))}
      </fieldset>
      <label className="field">
        <span>{draft.result === "passed" ? "Bemerkung / Protokollnummer" : "Festgestellte Mängel"}</span>
        <textarea className="textarea textarea-bordered" required={draft.result !== "passed"} rows={3} value={draft.notes} onChange={(event) => setDraft({ ...draft, notes: event.currentTarget.value })} />
      </label>
      {draft.result !== "passed" ? (
        <label className="plan-checkbox">
          <input checked={draft.create_follow_up} type="checkbox" onChange={(event) => setDraft({ ...draft, create_follow_up: event.currentTarget.checked })} />
          <span>Aufgabe zur Mängelbeseitigung anlegen{draft.result === "failed" ? " (dringend, Nachprüfung in 7 Tagen)" : ""}</span>
        </label>
      ) : null}
      {error ? <p className="panel-meta is-error" role="alert">{error}</p> : null}
      <button className="btn btn-primary" disabled={busy} type="submit">Nachweis speichern</button>
    </form>
  );
}
