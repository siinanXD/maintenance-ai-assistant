import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { MaintenancePlansApp } from "./MaintenancePlansApp";

const MAINTENANCE_ROOT_ID = "maintenance-plans-root";

/**
 * Mount the inspections and maintenance page.
 */
function bootstrapMaintenanceIsland(): void {
  const rootElement = document.getElementById(MAINTENANCE_ROOT_ID);
  if (!rootElement) return;
  createRoot(rootElement).render(
    <StrictMode>
      <MaintenancePlansApp />
    </StrictMode>
  );
}

bootstrapMaintenanceIsland();
