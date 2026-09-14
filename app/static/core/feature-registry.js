(function () {
  // Protected pages and the permission area each one needs. auth.js uses this
  // for the login redirect and the landing page after sign-in; the visible
  // navigation lives in frontend/src/layout/ShellNavigationModel.ts.
  const FEATURES = [
    { key: "dashboard", permissionKey: "dashboard", route: "/" },
    { key: "tasks", permissionKey: "tasks", route: "/tasks" },
    { key: "errors", permissionKey: "errors", route: "/errors" },
    { key: "employees", permissionKey: "employees", route: "/employees" },
    { key: "machines", permissionKey: "machines", route: "/machines", routePrefixes: ["/machines/"] },
    { key: "maintenance", permissionKey: "machines", route: "/maintenance" },
    { key: "inventory", permissionKey: "inventory", route: "/inventory" },
    { key: "shiftplans", permissionKey: "shiftplans", route: "/shiftplans" },
    { key: "handover", permissionKey: "shiftplans", route: "/handover" },
    { key: "vacations", permissionKey: "employees", route: "/vacations" },
    { key: "documents", permissionKey: "documents", route: "/documents" },
    { key: "admin_users", permissionKey: "admin_users", route: "/admin/users" },
    { key: "admin_ai", permissionKey: "admin_ai", route: "/admin/ai", routePrefixes: ["/admin/ai/"] },
  ];

  const byKey = Object.fromEntries(FEATURES.map((feature) => [feature.key, feature]));

  function featureForPath(pathname) {
    return FEATURES.find((feature) => (
      feature.route === pathname
      || (feature.routePrefixes || []).some((prefix) => pathname.startsWith(prefix))
    )) || null;
  }

  function permissionKeyFor(featureKey) {
    const feature = byKey[featureKey];
    return feature ? feature.permissionKey : featureKey;
  }

  window.maintenanceFeatures = {
    all: FEATURES,
    forPath: featureForPath,
    permissionKeyFor,
  };
})();
