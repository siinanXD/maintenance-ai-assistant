import { useState, type FormEvent, type ReactNode } from "react";

import { formatMoney } from "../../utils/number";
import { loadInventoryOptions, loadTaskMaterials, withdrawTaskMaterial, type InventoryOption, type TaskMaterials } from "../taskMaterialsApi";

type TaskMaterialsPanelProps = {
  readonly taskId: number;
  readonly open: boolean;
  readonly writable: boolean;
};

/**
 * Spare parts used on a work order: list with value and a withdrawal form.
 * Loads only when opened; the withdrawal form appears while the order is open.
 */
export function TaskMaterialsPanel({ taskId, open, writable }: TaskMaterialsPanelProps): ReactNode {
  const [materials, setMaterials] = useState<TaskMaterials | null>(null);
  const [options, setOptions] = useState<InventoryOption[]>([]);
  const [materialId, setMaterialId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [status, setStatus] = useState({ text: "", error: false });
  const [busy, setBusy] = useState(false);
  const canWithdraw = writable && open;

  /**
   * Load the booked parts and, for open orders, the stock to choose from.
   */
  async function refresh(): Promise<void> {
    try {
      const [booked, stock] = await Promise.all([
        loadTaskMaterials(taskId),
        canWithdraw ? loadInventoryOptions() : Promise.resolve([])
      ]);
      setMaterials(booked);
      setOptions(stock);
    } catch (error) {
      setMaterials({ items: [], total_value: 0 });
      setStatus({ text: error instanceof Error ? error.message : "Material konnte nicht geladen werden.", error: true });
    }
  }

  /**
   * Book the selected withdrawal.
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!materialId) return;
    setBusy(true);
    try {
      const movement = await withdrawTaskMaterial(taskId, Number(materialId), Number(quantity));
      setStatus({ text: `${Math.abs(movement.quantity_change)}× ${movement.material_name} entnommen.`, error: false });
      setMaterialId("");
      setQuantity("1");
      await refresh();
    } catch (error) {
      setStatus({ text: error instanceof Error ? error.message : "Entnahme fehlgeschlagen.", error: true });
    } finally {
      setBusy(false);
    }
  }

  const selected = options.find((option) => String(option.id) === materialId);

  return (
    <details
      className="attachment-panel task-materials-panel"
      onToggle={(event) => {
        if (event.currentTarget.open && materials === null) void refresh();
      }}
    >
      <summary>
        Material{materials && materials.items.length ? <span className="attachment-count">{formatMoney(materials.total_value)}</span> : null}
      </summary>
      <div className="attachment-body">
        {materials === null ? <p className="panel-meta">Wird geladen…</p> : null}
        {materials && !materials.items.length ? <p className="panel-meta">Noch kein Material gebucht.</p> : null}
        {materials && materials.items.length ? (
          <ul className="task-materials-list">
            {materials.items.map((item) => (
              <li key={item.id}>
                <span>{Math.abs(item.quantity_change)}× {item.material_name}</span>
                <small>{formatMoney(item.value)}{item.note ? ` · ${item.note}` : ""}</small>
              </li>
            ))}
          </ul>
        ) : null}
        {canWithdraw ? (
          <form className="task-materials-form" onSubmit={(event) => void handleSubmit(event)}>
            <label>
              <span>Ersatzteil</span>
              <select className="select select-bordered select-sm" required value={materialId} onChange={(event) => setMaterialId(event.currentTarget.value)}>
                <option value="">Auswählen…</option>
                {options.map((option) => (
                  <option disabled={option.quantity < 1} key={option.id} value={option.id}>
                    {option.name} ({option.quantity} auf Lager)
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Menge</span>
              <input className="input input-bordered input-sm" max={selected?.quantity || undefined} min={1} required type="number" value={quantity} onChange={(event) => setQuantity(event.currentTarget.value)} />
            </label>
            <button className="btn btn-outline btn-sm" disabled={busy || !materialId} type="submit">Entnehmen</button>
          </form>
        ) : null}
        {status.text ? <p className={`panel-meta${status.error ? " is-error" : ""}`} role="status">{status.text}</p> : null}
      </div>
    </details>
  );
}
