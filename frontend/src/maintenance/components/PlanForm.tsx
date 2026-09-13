import { useState, type FormEvent, type ReactNode } from "react";

import { savePlan } from "../maintenanceApi";
import type { MachineOption, MaintenancePlan, PlanDraft } from "../maintenanceTypes";

type PlanFormProps = {
  readonly draft: PlanDraft;
  readonly machines: readonly MachineOption[];
  readonly planId: number | null;
  readonly onDraftChange: (draft: PlanDraft) => void;
  readonly onSaved: (plan: MaintenancePlan) => Promise<void>;
};

const INTERVAL_PRESETS = [
  ["7", "wöchentlich"],
  ["30", "monatlich"],
  ["90", "vierteljährlich"],
  ["182", "halbjährlich"],
  ["365", "jährlich"],
  ["730", "alle 2 Jahre"],
  ["1460", "alle 4 Jahre"]
] as const;

/**
 * Create or edit a maintenance or inspection plan.
 */
export function PlanForm({ draft, machines, planId, onDraftChange, onSaved }: PlanFormProps): ReactNode {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  /**
   * Update one field of the draft.
   */
  function update<K extends keyof PlanDraft>(field: K, value: PlanDraft[K]): void {
    onDraftChange({ ...draft, [field]: value });
  }

  /**
   * Save the plan through the API.
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onSaved(await savePlan(draft, planId));
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Plan konnte nicht gespeichert werden.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="plan-form" onSubmit={(event) => void handleSubmit(event)}>
      <fieldset className="plan-kind-toggle">
        <legend>Art</legend>
        {(["inspection", "maintenance"] as const).map((kind) => (
          <label key={kind}>
            <input checked={draft.kind === kind} name="kind" type="radio" value={kind} onChange={() => update("kind", kind)} />
            <span>{kind === "inspection" ? "Prüfpflicht" : "Wartung"}</span>
          </label>
        ))}
      </fieldset>
      <label className="field">
        <span>Bezeichnung</span>
        <input className="input input-bordered" required maxLength={160} placeholder="z. B. Prüfung elektrischer Betriebsmittel" value={draft.title} onChange={(event) => update("title", event.currentTarget.value)} />
      </label>
      {draft.kind === "inspection" ? (
        <label className="field">
          <span>Rechtsgrundlage</span>
          <input className="input input-bordered" maxLength={120} placeholder="z. B. DGUV Vorschrift 3, BetrSichV §16" value={draft.legal_basis} onChange={(event) => update("legal_basis", event.currentTarget.value)} />
        </label>
      ) : null}
      <label className="field">
        <span>Maschine</span>
        <select className="select select-bordered" value={draft.machine_id} onChange={(event) => update("machine_id", event.currentTarget.value)}>
          <option value="">Keine bestimmte Maschine</option>
          {machines.map((machine) => <option key={machine.id} value={machine.id}>{machine.name}</option>)}
        </select>
      </label>
      <div className="plan-form-row">
        <label className="field">
          <span>Intervall</span>
          <select className="select select-bordered" value={INTERVAL_PRESETS.some(([days]) => days === draft.interval_days) ? draft.interval_days : "custom"} onChange={(event) => update("interval_days", event.currentTarget.value === "custom" ? "14" : event.currentTarget.value)}>
            {INTERVAL_PRESETS.map(([days, label]) => <option key={days} value={days}>{label}</option>)}
            <option value="custom">Eigene Tage…</option>
          </select>
        </label>
        {INTERVAL_PRESETS.some(([days]) => days === draft.interval_days) ? null : (
          <label className="field">
            <span>Tage</span>
            <input className="input input-bordered" min={1} required type="number" value={draft.interval_days} onChange={(event) => update("interval_days", event.currentTarget.value)} />
          </label>
        )}
        <label className="field">
          <span>Nächste Fälligkeit</span>
          <input className="input input-bordered" required type="date" value={draft.next_due_date} onChange={(event) => update("next_due_date", event.currentTarget.value)} />
        </label>
      </div>
      <label className="field">
        <span>Umfang und Hinweise</span>
        <textarea className="textarea textarea-bordered" rows={3} value={draft.description} onChange={(event) => update("description", event.currentTarget.value)} />
      </label>
      {error ? <p className="panel-meta is-error" role="alert">{error}</p> : null}
      <button className="btn btn-primary" disabled={busy} type="submit">{planId ? "Änderungen speichern" : "Plan anlegen"}</button>
    </form>
  );
}
