(async function () {
  "use strict";

  const STATIC_VERSION = window.maintenanceStaticVersion || "dev";
  await import("/static/pages/react-island-loader.js?v=" + STATIC_VERSION);
  const { waitForReactIsland } = window.MaintenanceReactIslandLoader;

  /**
   * Report a failed shiftplans React mount without loading the removed legacy runtime.
   *
   * @returns {void}
   */
  function reportShiftplansMountFailure() {
    if (window.maintenanceFrontend && window.maintenanceFrontend.setWorkflowStatus) {
      window.maintenanceFrontend.setWorkflowStatus(
        "Schichtplan konnte nicht als React-Seite geladen werden. Bitte Seite neu laden.",
        "error"
      );
    }
  }

  const reactMounted = await waitForReactIsland({
    mountedFlag: "maintenanceShiftplansReactMounted",
    mountEvent: "maintenance-shiftplans-react-mounted"
  });

  if (!reactMounted) reportShiftplansMountFailure();
})();
