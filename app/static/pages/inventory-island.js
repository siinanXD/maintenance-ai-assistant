(async function () {
  "use strict";

  const STATIC_VERSION = window.maintenanceStaticVersion || "dev";
  await import("/static/pages/react-island-loader.js?v=" + STATIC_VERSION);
  const { waitForReactIsland } = window.MaintenanceReactIslandLoader;

  /**
   * Report a failed inventory React mount without loading the removed legacy runtime.
   *
   * @returns {void}
   */
  function reportInventoryMountFailure() {
    if (window.maintenanceFrontend && window.maintenanceFrontend.setWorkflowStatus) {
      window.maintenanceFrontend.setWorkflowStatus(
        "Lager konnte nicht als React-Seite geladen werden. Bitte Seite neu laden.",
        "error"
      );
    }
  }

  const reactMounted = await waitForReactIsland({
    mountedFlag: "maintenanceInventoryReactMounted",
    mountEvent: "maintenance-inventory-react-mounted"
  });

  if (!reactMounted) reportInventoryMountFailure();
})();
