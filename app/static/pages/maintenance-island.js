(async function () {
  "use strict";

  const STATIC_VERSION = window.maintenanceStaticVersion || "dev";
  await import("/static/pages/react-island-loader.js?v=" + STATIC_VERSION);
  const { waitForReactIsland } = window.MaintenanceReactIslandLoader;

  const mounted = await waitForReactIsland({
    mountedFlag: "maintenanceMaintenanceReactMounted",
    mountEvent: "maintenance-maintenance-react-mounted"
  });

  if (!mounted) {
    console.error("Maintenance plans React island did not mount.");
  }
})();
