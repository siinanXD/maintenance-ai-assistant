(async function () {
  "use strict";

  const STATIC_VERSION = window.maintenanceStaticVersion || "dev";
  await import("/static/pages/react-island-loader.js?v=" + STATIC_VERSION);
  const { waitForReactIsland } = window.MaintenanceReactIslandLoader;

  /**
   * Report a failed employees React mount without loading the removed legacy runtime.
   *
   * @returns {void}
   */
  function reportEmployeesMountFailure() {
    if (window.maintenanceFrontend && window.maintenanceFrontend.setWorkflowStatus) {
      window.maintenanceFrontend.setWorkflowStatus(
        "Mitarbeiterseite konnte nicht als React-Seite geladen werden. Bitte Seite neu laden.",
        "error"
      );
    }
  }

  const reactMounted = await waitForReactIsland({
    mountedFlag: "maintenanceEmployeesReactMounted",
    mountEvent: "maintenance-employees-react-mounted"
  });

  if (!reactMounted) reportEmployeesMountFailure();
})();
