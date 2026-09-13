import { useState, type FormEvent, type ReactNode } from "react";

import { createMachine } from "../machineApi";
import type { MachineDraft, MessageState } from "../machineTypes";
import { EMPTY_MACHINE_DRAFT, machineErrorMessage } from "../machineUtils";

type MachineFormPanelProps = {
  readonly drawerMode?: boolean;
  readonly hidden: boolean;
  readonly onCreated: () => Promise<void>;
};

/**
 * Render the create machine form.
 */
export function MachineFormPanel({ drawerMode = false, hidden, onCreated }: MachineFormPanelProps): ReactNode {
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<MachineDraft>(EMPTY_MACHINE_DRAFT);
  const [message, setMessage] = useState<MessageState>({ text: "", error: false });
  const [open, setOpen] = useState(() => (
    drawerMode || typeof window.matchMedia !== "function"
      ? true
      : !window.matchMedia("(max-width: 639px)").matches
  ));

  /**
   * Keep the machine form expanded in drawer mode.
   */
  function handleToggle(openState: boolean): void {
    if (!drawerMode) {
      setOpen(openState);
    }
  }

  /**
   * Update one machine draft field.
   */
  function updateField(fieldName: keyof MachineDraft, value: string): void {
    setDraft((currentDraft) => ({ ...currentDraft, [fieldName]: value }));
  }

  /**
   * Persist the new machine.
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setMessage({ text: "Maschine wird gespeichert...", error: false });

    try {
      await createMachine(draft);
      setDraft(EMPTY_MACHINE_DRAFT);
      await onCreated();
      setMessage({ text: "Maschine gespeichert.", error: false });
    } catch (error) {
      setMessage({ text: machineErrorMessage(error), error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <details
      className="card app-card mobile-action-section lg:order-4 lg:col-span-12"
     
     
     
      hidden={hidden}
      onToggle={(event) => handleToggle(event.currentTarget.open)}
      open={drawerMode || open}
    >
      <summary className="mobile-action-summary">
        <span>
          <span className="mobile-action-title">Maschine anlegen</span>
          <span className="mobile-action-meta">Anlage und Produktionsdaten erfassen</span>
        </span>
      </summary>
      <form onSubmit={handleSubmit}>
        <div className="card-body">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Maschine anlegen</h2>
              <p className="panel-meta">Diese Daten werden auch für Schichtplanung und Anlagenzuordnung genutzt.</p>
            </div>
          </div>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="react-machine-name">Name</label>
              <input className="input input-bordered" disabled={busy} id="react-machine-name" name="name" onChange={(event) => updateField("name", event.target.value)} required value={draft.name} />
            </div>
            <div className="field">
              <label htmlFor="react-produced-item">Was wird produziert?</label>
              <input className="input input-bordered" disabled={busy} id="react-produced-item" name="produced_item" onChange={(event) => updateField("produced_item", event.target.value)} value={draft.produced_item} />
            </div>
            <div className="field">
              <label htmlFor="react-required-employees">Mitarbeiter pro Maschine</label>
              <input className="input input-bordered" disabled={busy} id="react-required-employees" min="1" name="required_employees" onChange={(event) => updateField("required_employees", event.target.value)} required type="number" value={draft.required_employees} />
            </div>
          </div>
          <div className="toolbar form-actions">
            <button className="btn btn-primary" disabled={busy} type="submit">
              {busy ? "Speichert..." : "Maschine speichern"}
            </button>
            <span className={`panel-meta${message.error ? " is-error" : ""}`}>
              {message.text}
            </span>
          </div>
        </div>
      </form>
    </details>
  );
}
