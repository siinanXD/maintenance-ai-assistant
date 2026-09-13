import { useMemo, useState, type ReactNode } from "react";

import { deleteMachine } from "../machineApi";
import type { Machine, MessageState } from "../machineTypes";
import { searchText } from "../machineUtils";

type MachineListProps = {
  readonly machines: readonly Machine[];
  readonly writable: boolean;
  readonly onEdit: (machine: Machine) => void;
  readonly onHistory: (machine: Machine) => Promise<void>;
  readonly onMessage: (message: MessageState) => void;
  readonly onRefresh: () => Promise<void>;
};

/**
 * Render one machine card.
 */
function MachineCard({
  machine,
  writable,
  onEdit,
  onHistory,
  onMessage,
  onRefresh
}: MachineListProps & { readonly machine: Machine }): ReactNode {
  const [busy, setBusy] = useState(false);

  /**
   * Delete one machine after confirmation.
   */
  async function handleDelete(): Promise<void> {
    const confirmed = window.confirm(`${machine.name} wirklich löschen? Zugeordnete Historie bleibt in den Fachseiten sichtbar.`);
    if (!confirmed) return;
    setBusy(true);
    try {
      await deleteMachine(machine.id);
      await onRefresh();
      onMessage({ text: "Maschine gelöscht.", error: false });
    } catch (error) {
      onMessage({ text: error instanceof Error ? error.message : "Maschine konnte nicht gelöscht werden.", error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <article
      className="record-card machine-record-card"
      data-search-text={[machine.name, machine.produced_item, machine.required_employees].filter(Boolean).join(" ")}
    >
      <div className="record-card-header">
        <div>
          <h3 className="record-card-title">{machine.name || "Maschine"}</h3>
          <p className="record-card-subtitle">{machine.produced_item || "Kein Produktionsinhalt hinterlegt"}</p>
        </div>
        {machine.active_errors ? (
          <span className="badge badge-status is-open">{machine.active_errors === 1 ? "1 Störung" : `${machine.active_errors} Störungen`}</span>
        ) : (
          <span className="badge badge-status is-done">In Betrieb</span>
        )}
      </div>
      <div className="record-card-meta">
        <span>
          <small>Personal</small>
          <strong>{machine.required_employees || 1} MA</strong>
        </span>
        <span>
          <small>Letzte Störung</small>
          <strong title={machine.last_error || undefined}>{machine.last_error || "Keine"}</strong>
        </span>
        <span>
          <small>Offene Aufgaben</small>
          <strong>{machine.open_tasks || 0}</strong>
        </span>
      </div>
      <div className="record-card-actions">
        <a className="btn btn-primary btn-sm" href={`/machines/${machine.id}`}>Profil</a>
        <button className="btn btn-outline btn-sm" disabled={busy} onClick={() => onHistory(machine)} type="button">Historie</button>
        {writable ? (
          <>
            <button className="btn btn-outline btn-sm" disabled={busy} onClick={() => onEdit(machine)} type="button">Bearbeiten</button>
            <button className="btn btn-ghost btn-sm" disabled={busy} onClick={handleDelete} type="button">
              {busy ? "Löscht..." : "Löschen"}
            </button>
          </>
        ) : null}
      </div>
    </article>
  );
}

/**
 * Render the machine list and local search.
 */
export function MachineList(props: MachineListProps): ReactNode {
  const [query, setQuery] = useState("");
  const filteredMachines = useMemo(() => {
    const normalizedQuery = searchText(query);
    if (!normalizedQuery) return props.machines;
    return props.machines.filter((machine) => (
      searchText([machine.name, machine.produced_item, machine.required_employees].filter(Boolean).join(" ")).includes(normalizedQuery)
    ));
  }, [props.machines, query]);

  return (
    <article className="card app-card mobile-primary-card lg:order-1 lg:col-span-12" id="machine-list">
      <div className="card-body">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Maschinenübersicht</h2>
            <p className="panel-meta">Anlagen, Personalbedarf und aktuelle Wartungshinweise</p>
          </div>
          <span className="badge badge-status is-open" data-machine-count>{props.machines.length} Maschinen</span>
        </div>
        <div className="list-toolbar">
          <label className="compact-search-field" htmlFor="react-machine-list-search">
            <span>Maschinen suchen</span>
            <input className="input input-bordered input-sm" data-list-search data-list-search-target="[data-machine-list]" id="react-machine-list-search" onChange={(event) => setQuery(event.target.value)} placeholder="Name, Produkt, Personalbedarf" value={query} />
          </label>
        </div>
        <div className="record-card-grid machine-card-grid" data-list-search-items=".record-card" data-machine-list>
          {filteredMachines.length ? (
            filteredMachines.map((machine) => <MachineCard key={machine.id} {...props} machine={machine} />)
          ) : (
            <article className="guided-empty-state empty-state">
              <strong>Noch keine Maschinen vorhanden.</strong>
              <p>{props.writable ? "Lege die erste Maschine an, damit Aufgaben, Störungen und Dokumente sauber zugeordnet werden." : "Sobald Maschinen angelegt sind, erscheinen sie hier mit Status und Schnellaktionen."}</p>
            </article>
          )}
        </div>
      </div>
    </article>
  );
}
