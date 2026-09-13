import { useEffect, useState, type ReactNode } from "react";

import { markIslandMounted } from "../app/islandMount";
import { canWriteDashboard } from "../auth/permissions";
import { ActionDrawer } from "../components/ui/ActionDrawer";
import { createActionDefinition } from "../components/ui/createActionSchema";
import { InventoryForecastPanel } from "./components/InventoryForecastPanel";
import { InventoryHeader } from "./components/InventoryHeader";
import { InventoryList } from "./components/InventoryList";
import { InventoryStats } from "./components/InventoryStats";
import { MaterialForm } from "./components/MaterialForm";
import { ReorderPanel } from "./components/ReorderPanel";
import {
  calculateInventoryForecast,
  loadInventoryMaterials,
  loadMachines,
  loadReorderSuggestions
} from "./inventoryApi";
import type { InventoryForecast, InventoryMaterial, Machine, ReorderSuggestions } from "./inventoryTypes";
import { inventoryErrorMessage } from "./inventoryUtils";

const INVENTORY_ISLAND = {
  mountedFlag: "maintenanceInventoryReactMounted",
  mountEvent: "maintenance-inventory-react-mounted"
};

/**
 * Render the React inventory workflow island.
 */
export function InventoryApp(): ReactNode {
  const writable = canWriteDashboard("inventory");
  const [isCreateDrawerOpen, setIsCreateDrawerOpen] = useState(false);
  const [materials, setMaterials] = useState<InventoryMaterial[]>([]);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [forecast, setForecast] = useState<InventoryForecast | null>(null);
  const [threshold, setThreshold] = useState(5);
  const [loadError, setLoadError] = useState("");
  const [reorder, setReorder] = useState<ReorderSuggestions | null>(null);

  /**
   * Refresh inventory and machine data in parallel.
   */
  async function refreshInventory(): Promise<void> {
    const [loadedMaterials, loadedMachines, loadedReorder] = await Promise.all([
      loadInventoryMaterials(),
      loadMachines(),
      loadReorderSuggestions()
    ]);
    setMaterials(loadedMaterials);
    setMachines(loadedMachines);
    setReorder(loadedReorder);
  }

  /**
   * Run the inventory forecast request.
   */
  async function runForecast(nextThreshold: number): Promise<void> {
    const result = await calculateInventoryForecast({
      low_stock_threshold: nextThreshold,
      status: "open",
      limit: 20
    });
    setForecast(result);
  }

  useEffect(() => {
    markIslandMounted(INVENTORY_ISLAND);
  }, []);

  useEffect(() => {
    refreshInventory().catch((error: unknown) => {
      setLoadError(inventoryErrorMessage(error));
    });
    if (window.location.hash === "#inventory-create") {
      setIsCreateDrawerOpen(true);
    }
  }, []);

  return (
    <>
      <InventoryHeader onCreateMaterial={() => setIsCreateDrawerOpen(true)} writable={writable} />
      {loadError ? (
        <section className="card app-card" role="alert">
          <div className="card-body">
            <p className="panel-meta is-error">{loadError}</p>
          </div>
        </section>
      ) : null}
      <InventoryStats materials={materials} />
      <section className="dashboard-grid">
        <ReorderPanel suggestions={reorder} />
        <InventoryForecastPanel
          forecast={forecast}
          onForecast={runForecast}
          onThresholdChange={setThreshold}
          threshold={threshold}
        />
        <InventoryList materials={materials} onRefresh={refreshInventory} writable={writable} />
      </section>
      <ActionDrawer
        definition={createActionDefinition("inventoryMaterialCreate")}
        isOpen={isCreateDrawerOpen}
        onClose={() => setIsCreateDrawerOpen(false)}
      >
        <MaterialForm
          drawerMode
          machines={machines}
          onCreated={async () => {
            await refreshInventory();
            setIsCreateDrawerOpen(false);
          }}
        />
      </ActionDrawer>
    </>
  );
}
