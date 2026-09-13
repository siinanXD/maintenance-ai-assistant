(function () {
  const FEATURES = [
    {
      key: "dashboard",
      permissionKey: "dashboard",
      label: "Cockpit",
      route: "/",
      group: "Cockpit",
      module: "page",
      moduleUrl: "/static/pages/dashboard-island.js",
    },
    {
      key: "tasks",
      permissionKey: "tasks",
      label: "Aufgaben",
      route: "/tasks",
      group: "Arbeit",
      module: "page",
      moduleUrl: "/static/pages/tasks-island.js",
    },
    {
      key: "errors",
      permissionKey: "errors",
      label: "Fehlerliste",
      route: "/errors",
      group: "Arbeit",
      module: "page",
      moduleUrl: "/static/pages/errors-island.js",
    },
    {
      key: "employees",
      permissionKey: "employees",
      label: "Mitarbeiter",
      route: "/employees",
      group: "Planung & Personal",
      module: "page",
      moduleUrl: "/static/pages/employees-island.js",
    },
    {
      key: "machines",
      permissionKey: "machines",
      label: "Maschinen",
      route: "/machines",
      routePrefixes: ["/machines/"],
      group: "Anlagen & Material",
      module: "page",
      moduleUrl: "/static/pages/machines-island.js",
    },
    {
      key: "maintenance",
      permissionKey: "machines",
      label: "Prüfungen & Wartung",
      route: "/maintenance",
      group: "Arbeit",
      module: "page",
      moduleUrl: "/static/pages/maintenance-island.js",
    },
    {
      key: "inventory",
      permissionKey: "inventory",
      label: "Lager",
      route: "/inventory",
      group: "Anlagen & Material",
      module: "page",
      moduleUrl: "/static/pages/inventory-island.js",
    },
    {
      key: "shiftplans",
      permissionKey: "shiftplans",
      label: "Schichtplan",
      route: "/shiftplans",
      group: "Planung & Personal",
      module: "page",
      moduleUrl: "/static/pages/shiftplans-island.js",
    },
    {
      key: "handover",
      permissionKey: "shiftplans",
      label: "Schichtübergabe",
      route: "/handover",
      group: "Arbeit",
      module: "page",
      moduleUrl: "/static/pages/handover-island.js",
    },
    {
      key: "vacations",
      permissionKey: "employees",
      label: "Urlaubsplanung",
      route: "/vacations",
      group: "Planung & Personal",
      module: "page",
      moduleUrl: "/static/pages/vacations-island.js",
    },
    {
      key: "documents",
      permissionKey: "documents",
      label: "Dokumente",
      route: "/documents",
      group: "Anlagen & Material",
      module: "page",
      moduleUrl: "/static/pages/documents-island.js",
    },
    {
      key: "admin_users",
      permissionKey: "admin_users",
      label: "Benutzer",
      route: "/admin/users",
      group: "Administration",
      module: "page",
      moduleUrl: "/static/pages/admin-users-island.js",
    },
    {
      key: "admin_ai",
      permissionKey: "admin_ai",
      label: "KI-Administration",
      route: "/admin/ai",
      routeAliases: [
        "/admin/ai/rag-board",
        "/admin/ai/source-check",
        "/admin/ai/prompt-faq",
        "/admin/ai/effectiveness",
        "/admin/ai/technical",
        // Deprecated legacy Admin-AI aliases kept for old bookmarks and redirects.
        "/admin/ai/prompts",
        "/admin/ai/faq",
        "/admin/ai/lab",
        "/admin/ai/costs",
        "/admin/ai/feedback",
        "/admin/ai/models",
        "/admin/ai/knowledge",
        "/admin/ai/training",
        "/admin/ai/retrieval",
        "/admin/ai/diagnostics",
        "/admin/ai/indexing"
      ],
      group: "Administration",
      module: "page",
      moduleUrl: "/static/pages/admin-ai-island.js",
    },
  ];

  const byKey = Object.fromEntries(FEATURES.map((feature) => [feature.key, feature]));
  const byRoute = Object.fromEntries(FEATURES.map((feature) => [feature.route, feature]));

  function getFeature(featureKey) {
    return byKey[featureKey] || null;
  }

  function featureForPath(pathname) {
    const directFeature = byRoute[pathname];
    if (directFeature) return directFeature;
    return FEATURES.find((feature) => {
      if (Array.isArray(feature.routeAliases) && feature.routeAliases.includes(pathname)) {
        return true;
      }
      return Array.isArray(feature.routePrefixes) && feature.routePrefixes.some((prefix) => (
        pathname.startsWith(prefix)
      ));
    }) || null;
  }

  function permissionKeyFor(featureKey) {
    const feature = getFeature(featureKey);
    return feature ? feature.permissionKey : featureKey;
  }

  window.maintenanceFeatures = {
    all: FEATURES,
    keys: FEATURES.map((feature) => feature.key),
    get: getFeature,
    forPath: featureForPath,
    permissionKeyFor,
    destinations: Object.fromEntries(
      FEATURES.map((feature) => [feature.key, feature.route])
    ),
  };
})();
