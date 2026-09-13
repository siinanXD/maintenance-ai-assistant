(async function () {
  "use strict";

  const STATIC_VERSION = window.maintenanceStaticVersion || "dev";
  await import("/static/pages/react-island-loader.js?v=" + STATIC_VERSION);
  const { waitForReactIsland } = window.MaintenanceReactIslandLoader;

  /**
   * Report a failed Admin-AI React mount without loading the removed legacy runtime.
   *
   * @returns {void}
   */
  function reportAdminAiMountFailure() {
    if (window.maintenanceFrontend && window.maintenanceFrontend.setWorkflowStatus) {
      window.maintenanceFrontend.setWorkflowStatus(
        "KI-Administration konnte nicht als React-Seite geladen werden. Bitte Seite neu laden.",
        "error"
      );
    }
  }

  const reactMounted = await waitForReactIsland({
    mountedFlag: "maintenanceAdminAiReactMounted",
    mountEvent: "maintenance-admin-ai-react-mounted"
  });

  if (!reactMounted) reportAdminAiMountFailure();
})();
