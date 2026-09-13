import { useMemo, useState, type FormEvent, type ReactNode } from "react";

import { bookGoodsReceipt, deleteInventoryMaterial } from "../inventoryApi";
import type { InventoryMaterial } from "../inventoryTypes";
import { formatMoney } from "../../formatters/number";
import { materialSearchText, searchText } from "../inventoryUtils";

type InventoryListProps = {
  readonly materials: readonly InventoryMaterial[];
  readonly writable: boolean;
  readonly onRefresh: () => Promise<void>;
};

/**
 * Render one inventory material card.
 */
function MaterialCard({
  material,
  writable,
  onChanged
}: {
  readonly material: InventoryMaterial;
  readonly writable: boolean;
  readonly onChanged: () => Promise<void>;
}): ReactNode {
  const [busy, setBusy] = useState(false);
  const [receiptOpen, setReceiptOpen] = useState(false);
  const [receiptQuantity, setReceiptQuantity] = useState("1");
  const [receiptNote, setReceiptNote] = useState("");
  const quantity = Number(material.quantity || 0);
  const minimum = Number(material.min_quantity || 0);
  const isLow = minimum > 0 && quantity <= minimum;
  const machineName = material.machine?.name || "Keine Maschine";

  /**
   * Book a goods receipt for this material.
   */
  async function handleReceipt(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setBusy(true);
    try {
      await bookGoodsReceipt(material.id, Number(receiptQuantity), receiptNote);
      setReceiptOpen(false);
      setReceiptQuantity("1");
      setReceiptNote("");
      await onChanged();
    } finally {
      setBusy(false);
    }
  }

  /**
   * Delete a material after user confirmation.
   */
  async function handleDelete(): Promise<void> {
    if (!window.confirm(`${material.name} wirklich löschen?`)) {
      return;
    }

    setBusy(true);
    try {
      await deleteInventoryMaterial(material.id);
      await onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className={`record-card inventory-card${isLow ? " is-low-stock" : ""}`} data-search-text={searchText(materialSearchText(material))}>
      <div className="record-card-header">
        <div>
          <h3 className="record-card-title">{material.name || "Material"}</h3>
          <p className="record-card-subtitle">{[material.manufacturer || "Hersteller offen", machineName].join(" · ")}</p>
        </div>
        <span className={isLow ? "badge badge-priority is-soon" : "badge badge-status is-done"}>
          {isLow ? "nachbestellen" : "verfügbar"}
        </span>
      </div>
      <div className="record-card-meta inventory-card-meta">
        {[
          ["Bestand", minimum ? `${quantity} / min. ${minimum}` : String(quantity)],
          ["Einzelkosten", formatMoney(material.unit_cost)],
          ["Gesamtwert", formatMoney(material.total_value)],
          ["Lieferzeit", material.lead_time_days ? `${material.lead_time_days} Tage` : "–"]
        ].map(([label, value]) => (
          <span key={label}>
            <small>{label}</small>
            <strong>{value || "-"}</strong>
          </span>
        ))}
      </div>
      {receiptOpen ? (
        <form className="inventory-receipt-form" onSubmit={(event) => void handleReceipt(event)}>
          <label>
            <span>Menge</span>
            <input className="input input-bordered input-sm" min={1} required type="number" value={receiptQuantity} onChange={(event) => setReceiptQuantity(event.currentTarget.value)} />
          </label>
          <label>
            <span>Lieferschein</span>
            <input className="input input-bordered input-sm" maxLength={200} placeholder="optional" value={receiptNote} onChange={(event) => setReceiptNote(event.currentTarget.value)} />
          </label>
          <button className="btn btn-primary btn-sm" disabled={busy} type="submit">Buchen</button>
          <button className="btn btn-ghost btn-sm" type="button" onClick={() => setReceiptOpen(false)}>Abbrechen</button>
        </form>
      ) : null}
      <div className="record-card-actions">
        {writable && !receiptOpen ? (
          <button className="btn btn-outline btn-sm" disabled={busy} onClick={() => setReceiptOpen(true)} type="button">
            Wareneingang
          </button>
        ) : null}
        {material.machine?.id ? (
          <a className="btn btn-outline btn-sm" href={`/machines/${material.machine.id}`}>Maschinenprofil</a>
        ) : null}
        {writable ? (
          <button className="btn btn-ghost btn-sm" disabled={busy} onClick={handleDelete} type="button">
            Löschen
          </button>
        ) : null}
      </div>
    </article>
  );
}

/**
 * Render the inventory list and local search.
 */
export function InventoryList({ materials, writable, onRefresh }: InventoryListProps): ReactNode {
  const [query, setQuery] = useState("");
  const filteredMaterials = useMemo(() => {
    const normalizedQuery = searchText(query);
    if (!normalizedQuery) {
      return materials;
    }

    return materials.filter((material) => searchText(materialSearchText(material)).includes(normalizedQuery));
  }, [materials, query]);

  return (
    <article className="card app-card mobile-primary-card lg:order-1 lg:col-span-12" id="inventory-list">
      <div className="card-body">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Lagerbestand</h2>
            <p className="panel-meta">Materialien, Mengen und Gesamtwert je Position</p>
          </div>
        </div>
        <div className="list-toolbar">
          <label className="compact-search-field" htmlFor="react-inventory-list-search">
            <span>Material suchen</span>
            <input className="input input-bordered input-sm" data-list-search data-list-search-target="[data-inventory-list]" id="react-inventory-list-search" onChange={(event) => setQuery(event.target.value)} placeholder="Name, Maschine, Hersteller" value={query} />
          </label>
        </div>
        <div className="record-card-grid inventory-card-grid bounded-list-scroll" data-inventory-list data-list-search-items=".inventory-card">
          {filteredMaterials.length ? (
            filteredMaterials.map((material) => (
              <MaterialCard key={material.id} material={material} onChanged={onRefresh} writable={writable} />
            ))
          ) : (
            <div className="empty-state">
              <strong>Noch kein Material angelegt.</strong>
              <span>Lege die ersten Ersatzteile an, damit Lagerwert und Maschinenbezug sichtbar werden.</span>
            </div>
          )}
        </div>
      </div>
    </article>
  );
}
