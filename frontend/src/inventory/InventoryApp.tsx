import { useEffect, useState, type ReactNode } from "react";

import { canViewDashboard, canWriteDashboard } from "../auth/permissions";
import { ActionDrawer } from "../components/ui/ActionDrawer";
import { createActionDefinition } from "../components/ui/createActionSchema";
import { PageHeader } from "../components/ui/PageHeader";
import { StatStrip } from "../components/ui/StatStrip";
import { InventoryForecastPanel } from "./components/InventoryForecastPanel";
import { InventoryList } from "./components/InventoryList";
import { MaterialForm } from "./components/MaterialForm";
import { ReorderPanel } from "./components/ReorderPanel";
import {
  calculateInventoryForecast,
  loadInventoryMaterials,
  loadMachines,
  loadReorderSuggestions
} from "./inventoryApi";
import type { InventoryForecast, InventoryMaterial, Machine, ReorderSuggestions } from "./inventoryTypes";
import { inventoryErrorMessage, inventoryStats } from "./inventoryUtils";

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
  const stats = inventoryStats(materials);

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
    refreshInventory().catch((error: unknown) => {
      setLoadError(inventoryErrorMessage(error));
    });
    if (window.location.hash === "#inventory-create") {
      setIsCreateDrawerOpen(true);
    }
  }, []);

  return (
    <>
      <PageHeader
        title="Lager"
        description="Materialien mit Kosten, Anzahl, Hersteller und verbauter Maschine verwalten."
        actions={[
          { hidden: !writable, onClick: () => setIsCreateDrawerOpen(true), schema: createActionDefinition("inventoryMaterialCreate"), variant: "primary" },
          { label: "Prognose berechnen", onClick: () => void runForecast(threshold) },
          { hidden: !canViewDashboard("machines"), href: "/machines", label: "Maschinen", variant: "ghost" }
        ]}
      />
      {loadError ? (
        <section className="card app-card" role="alert">
          <div className="card-body">
            <p className="panel-meta is-error">{loadError}</p>
          </div>
        </section>
      ) : null}
      <StatStrip
        label="Lagerstatus"
        stats={[
          { label: "Positionen", value: stats.count, meta: "Materialien mit Hersteller und Maschine" },
          { label: "Mindestbestand", value: stats.lowStock, meta: "auf oder unter dem Mindestbestand", tone: stats.lowStock ? "warning" : "neutral" },
          { label: "Lagerwert", value: stats.totalValue, meta: "Bestand × Einzelkosten" }
        ]}
      />
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
