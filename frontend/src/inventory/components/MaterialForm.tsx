import { useState, type FormEvent, type ReactNode } from "react";

import {
  createInventoryMaterial,
  type CreateMaterialPayload
} from "../inventoryApi";
import type { Machine } from "../inventoryTypes";
import { inventoryErrorMessage, type MessageState } from "../inventoryUtils";

type MaterialFormProps = {
  readonly drawerMode?: boolean;
  readonly machines: readonly Machine[];
  readonly onCreated: () => Promise<void>;
};

type MaterialFormState = {
  readonly name: string;
  readonly unit_cost: string;
  readonly quantity: string;
  readonly manufacturer: string;
  readonly machine_id: string;
};

const EMPTY_FORM: MaterialFormState = {
  name: "",
  unit_cost: "",
  quantity: "",
  manufacturer: "",
  machine_id: ""
};

/**
 * Render the material creation form.
 */
export function MaterialForm({ drawerMode = false, machines, onCreated }: MaterialFormProps): ReactNode {
  const [formState, setFormState] = useState<MaterialFormState>(EMPTY_FORM);
  const [message, setMessage] = useState<MessageState>({ text: "", error: false });
  const [open, setOpen] = useState(() => (
    drawerMode || typeof window.matchMedia !== "function"
      ? true
      : !window.matchMedia("(max-width: 639px)").matches
  ));

  /**
   * Update the disclosure state unless the drawer owns visibility.
   */
  function handleToggle(openState: boolean): void {
    if (!drawerMode) {
      setOpen(openState);
    }
  }
  const [busy, setBusy] = useState(false);

  /**
   * Update one controlled material field.
   */
  function updateField(fieldName: keyof MaterialFormState, value: string): void {
    setFormState((currentState) => ({ ...currentState, [fieldName]: value }));
  }

  /**
   * Build the API payload for material creation.
   */
  function createPayload(): CreateMaterialPayload {
    if (!formState.name.trim()) {
      throw new Error("name is required");
    }

    return {
      name: formState.name.trim(),
      unit_cost: Number(formState.unit_cost || 0),
      quantity: Number(formState.quantity || 0),
      manufacturer: formState.manufacturer.trim(),
      machine_id: formState.machine_id ? Number(formState.machine_id) : null
    };
  }

  /**
   * Submit a new inventory material.
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setMessage({ text: "Material wird gespeichert...", error: false });

    try {
      await createInventoryMaterial(createPayload());
      setFormState(EMPTY_FORM);
      await onCreated();
      setMessage({ text: "Material gespeichert.", error: false });
    } catch (error) {
      setMessage({ text: inventoryErrorMessage(error), error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <details
      className="card app-card mobile-action-section lg:order-3 lg:col-span-12"
     
     
     
      onToggle={(event) => handleToggle(event.currentTarget.open)}
      open={drawerMode || open}
    >
      <summary className="mobile-action-summary">
        <span>
          <span className="mobile-action-title">Material anlegen</span>
          <span className="mobile-action-meta">Bestand und Wert erfassen</span>
        </span>
      </summary>
      <form onSubmit={handleSubmit}>
        <div className="card-body">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Material anlegen</h2>
              <p className="panel-meta">Bestand und Wert werden automatisch im Cockpit summiert.</p>
            </div>
          </div>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="react-material-name">Name</label>
              <input className="input input-bordered" disabled={busy} id="react-material-name" name="name" onChange={(event) => updateField("name", event.target.value)} required value={formState.name} />
            </div>
            <div className="field">
              <label htmlFor="react-unit-cost">Kosten pro Stück</label>
              <input className="input input-bordered" disabled={busy} id="react-unit-cost" min="0" name="unit_cost" onChange={(event) => updateField("unit_cost", event.target.value)} required step="0.01" type="number" value={formState.unit_cost} />
            </div>
            <div className="field">
              <label htmlFor="react-quantity">Anzahl</label>
              <input className="input input-bordered" disabled={busy} id="react-quantity" min="0" name="quantity" onChange={(event) => updateField("quantity", event.target.value)} required type="number" value={formState.quantity} />
            </div>
            <div className="field">
              <label htmlFor="react-manufacturer">Hersteller</label>
              <input className="input input-bordered" disabled={busy} id="react-manufacturer" name="manufacturer" onChange={(event) => updateField("manufacturer", event.target.value)} value={formState.manufacturer} />
            </div>
            <div className="field">
              <label htmlFor="react-material-machine">Verbaut an Maschine</label>
              <select className="select select-bordered" disabled={busy} id="react-material-machine" name="machine_id" onChange={(event) => updateField("machine_id", event.target.value)} value={formState.machine_id}>
                <option value="">Keine Maschine</option>
                {machines.map((machine) => (
                  <option key={machine.id} value={machine.id}>{machine.name}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="toolbar form-actions">
            <button className="btn btn-primary" disabled={busy} type="submit">
              {busy ? "Speichert..." : "Material speichern"}
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
