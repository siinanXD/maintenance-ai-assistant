import {
  useEffect,
  useState,
  type ReactNode
} from "react";

import { markIslandMounted } from "../app/islandMount";
import { canWriteDashboard } from "../auth/permissions";
import { ActionDrawer } from "../components/ui/ActionDrawer";
import { createActionDefinition } from "../components/ui/createActionSchema";
import {
  loadMachineHistory,
  loadMachines,
  loadMaintenanceRecommendations
} from "./machineApi";
import { MachineEditDialog } from "./components/MachineEditDialog";
import { MachineFormPanel } from "./components/MachineFormPanel";
import { MachineHistoryPanel } from "./components/MachineHistoryPanel";
import { MachineList } from "./components/MachineList";
import { MachineStats } from "./components/MachineStats";
import { MachinesHeader } from "./components/MachinesHeader";
import { MaintenanceRecommendations } from "./components/MaintenanceRecommendations";
import type {
  Machine,
  MachineHistory,
  MachineRecommendation,
  MessageState
} from "./machineTypes";
import { machineErrorMessage } from "./machineUtils";

const MACHINES_OVERVIEW_ISLAND = {
  mountedFlag: "maintenanceMachinesReactMounted",
  mountEvent: "maintenance-machines-react-mounted"
};

/**
 * Render the React machines overview island.
 */
export function MachinesOverviewApp(): ReactNode {
  const writable = canWriteDashboard("machines");
  const [isCreateDrawerOpen, setIsCreateDrawerOpen] = useState(false);
  const [editingMachine, setEditingMachine] = useState<Machine | null>(null);
  const [history, setHistory] = useState<MachineHistory | null>(null);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [message, setMessage] = useState<MessageState>({ text: "", error: false });
  const [recommendations, setRecommendations] = useState<MachineRecommendation[]>([]);
  const issueCount = machines.reduce((total, machine) => total + (machine.active_errors || 0), 0);

  /**
   * Refresh overview data.
   */
  async function refreshMachines(): Promise<void> {
    setMachines(await loadMachines());
  }

  /**
   * Refresh recommendation data.
   */
  async function refreshRecommendations(): Promise<void> {
    try {
      setRecommendations(await loadMaintenanceRecommendations());
    } catch (error) {
      setMessage({ text: `Präventive Wartung konnte nicht geladen werden: ${machineErrorMessage(error)}`, error: true });
    }
  }

  /**
   * Load history for one machine.
   */
  async function showMachineHistory(machine: Machine): Promise<void> {
    setHistory(await loadMachineHistory(machine.id));
    window.requestAnimationFrame(() => {
      document.querySelector("[data-machine-history-panel]")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  /**
   * Load history by machine id.
   */
  async function showMachineHistoryById(machineId: number): Promise<void> {
    setHistory(await loadMachineHistory(machineId));
    window.requestAnimationFrame(() => {
      document.querySelector("[data-machine-history-panel]")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  /**
   * Focus the active assistant area or first history button.
   */
  function focusAssistant(): void {
    if (!history) {
      document.querySelector<HTMLElement>("[data-machine-list] button")?.focus();
      return;
    }
    document.querySelector("[data-machine-assistant-form]")?.scrollIntoView({ behavior: "smooth", block: "center" });
    document.querySelector<HTMLInputElement>("[data-machine-assistant-form] input")?.focus();
  }

  useEffect(() => {
    markIslandMounted(MACHINES_OVERVIEW_ISLAND);
  }, []);

  useEffect(() => {
    refreshMachines().catch((error: unknown) => {
      setMessage({ text: machineErrorMessage(error), error: true });
    });
    refreshRecommendations();
    if (window.location.hash === "#machine-create") {
      setIsCreateDrawerOpen(true);
    }
  }, []);

  return (
    <>
      <MachinesHeader
        issueCount={issueCount}
        onAssistantFocus={focusAssistant}
        onCreateMachine={() => setIsCreateDrawerOpen(true)}
        writable={writable}
      />
      <MachineStats issueCount={issueCount} machines={machines} />
      {message.text ? (
        <section className="card app-card" role="alert">
          <div className="card-body">
            <p className={`panel-meta${message.error ? " is-error" : ""}`}>{message.text}</p>
          </div>
        </section>
      ) : null}
      <section className="dashboard-grid">
        <MaintenanceRecommendations onHistory={showMachineHistoryById} recommendations={recommendations} />
        <MachineHistoryPanel history={history} />
        <MachineList
          machines={machines}
          onEdit={setEditingMachine}
          onHistory={showMachineHistory}
          onMessage={setMessage}
          onRefresh={refreshMachines}
          writable={writable}
        />
      </section>
      <MachineEditDialog machine={editingMachine} onClose={() => setEditingMachine(null)} onSaved={refreshMachines} />
      <ActionDrawer
        definition={createActionDefinition("machineCreate")}
        isOpen={isCreateDrawerOpen}
        onClose={() => setIsCreateDrawerOpen(false)}
      >
        <MachineFormPanel
          drawerMode
          hidden={!writable}
          onCreated={async () => {
            await refreshMachines();
            setIsCreateDrawerOpen(false);
          }}
        />
      </ActionDrawer>
    </>
  );
}
