(function () {
  // Session store and page guard. React reads the session through
  // window.maintenanceAuth (frontend/src/app/runtimeBridge.ts) and renders
  // navigation, menus and permission-dependent controls itself.
  const TOKEN_KEY = "maintenance_access_token";
  const USER_KEY = "maintenance_user";
  const CONTRAST_KEY = "maintenance_high_contrast";

  function hasToken() {
    return Boolean(window.localStorage.getItem(TOKEN_KEY));
  }

  function isAdminUser(user) {
    return Boolean(user && user.role === "master_admin");
  }

  const featureRegistry = window.maintenanceFeatures || { all: [] };
  const DASHBOARD_DESTINATIONS = Object.fromEntries(
    featureRegistry.all.map((feature) => [feature.key, feature.route])
  );
  const DASHBOARD_ORDER = featureRegistry.all.map((feature) => feature.key);

  function permissionFor(user, dashboard) {
    if (isAdminUser(user)) return { can_view: true, can_write: true, employee_access_level: "confidential" };
    const permissionKey = featureRegistry.permissionKeyFor
      ? featureRegistry.permissionKeyFor(dashboard)
      : dashboard;
    return (user && user.permissions && user.permissions[permissionKey]) || {};
  }

  function canView(user, dashboard) {
    return Boolean(permissionFor(user, dashboard).can_view);
  }

  function canWrite(user, dashboard) {
    return Boolean(permissionFor(user, dashboard).can_write);
  }

  function employeeAccessLevel(user) {
    return permissionFor(user, "employees").employee_access_level || "none";
  }

  function destinationForUser(user) {
    const firstDashboard = DASHBOARD_ORDER.find((dashboard) => canView(user, dashboard));
    return DASHBOARD_DESTINATIONS[firstDashboard] || "/login";
  }

  function dashboardForPath(pathname) {
    const feature = featureRegistry.forPath ? featureRegistry.forPath(pathname) : null;
    return feature ? feature.key : null;
  }

  function currentPathWithSearch() {
    return window.location.pathname + window.location.search;
  }

  function loginUrlFor(path) {
    const params = new URLSearchParams();
    params.set("next", path || currentPathWithSearch());
    return "/login?" + params.toString();
  }

  function destinationForUserOrNext(user, nextPath) {
    let normalizedNext = nextPath || "";
    try {
      const nextUrl = new URL(normalizedNext, window.location.origin);
      if (nextUrl.origin !== window.location.origin) {
        return destinationForUser(user);
      }
      normalizedNext = nextUrl.pathname + nextUrl.search;
    } catch (error) {
      return destinationForUser(user);
    }
    const dashboard = dashboardForPath(new URL(normalizedNext, window.location.origin).pathname);
    if (dashboard && canView(user, dashboard)) {
      return normalizedNext;
    }
    return destinationForUser(user);
  }

  function currentUser() {
    try {
      return JSON.parse(window.localStorage.getItem(USER_KEY) || "null");
    } catch (error) {
      return null;
    }
  }

  async function refreshUser() {
    const authToken = window.localStorage.getItem(TOKEN_KEY);
    if (!authToken) return null;

    try {
      const response = await fetch("/api/v1/auth/me", {
        headers: { "Authorization": "Bearer " + authToken }
      });
      if (!response.ok) {
        if (response.status === 401 || response.status === 422) clearSession({ redirect: true });
        return null;
      }
      const responseData = await response.json();
      const freshUser = responseData && responseData.success === true && Object.prototype.hasOwnProperty.call(responseData, "data")
        ? responseData.data
        : responseData;
      window.localStorage.setItem(USER_KEY, JSON.stringify(freshUser));
      updateAuthUi();
      return freshUser;
    } catch (error) {
      return currentUser();
    }
  }

  function clearSession(options) {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
    window.dispatchEvent(new Event("maintenance-auth-changed"));
    updateAuthUi();
    if (options && options.redirect && window.location.pathname !== "/login") {
      window.location.href = loginUrlFor(currentPathWithSearch());
    }
  }

  async function logout() {
    const authToken = window.localStorage.getItem(TOKEN_KEY);
    try {
      if (authToken) {
        const response = await fetch("/api/v1/auth/logout", {
          method: "POST",
          headers: { "Authorization": "Bearer " + authToken },
          keepalive: true
        });
        if (!response.ok && response.status !== 401 && response.status !== 422) {
          throw new Error("Logout failed with status " + response.status);
        }
      }
    } catch (error) {
      console.warn("Logout token revocation failed.", error);
    } finally {
      clearSession({ redirect: true });
    }
  }

  function applyContrastPreference() {
    const enabled = window.localStorage.getItem(CONTRAST_KEY) === "true";
    document.documentElement.classList.toggle("high-contrast", enabled);
    document.body.classList.toggle("high-contrast", enabled);
  }

  let authReadyPromise;

  async function ensureAuthReady() {
    if (!authReadyPromise) {
      authReadyPromise = (async () => {
        updateAuthUi();
        if (hasToken()) {
          refreshUser();
        }
        window.dispatchEvent(new Event("maintenance-auth-ready"));
        return currentUser();
      })();
    }
    return authReadyPromise;
  }

  function updateAuthUi() {
    const loggedIn = hasToken();
    const user = currentUser();
    document.body.classList.toggle("is-authenticated", loggedIn);
    document.body.classList.toggle("is-admin", isAdminUser(user));
    applyContrastPreference();

    const requiredDashboard = dashboardForPath(window.location.pathname);
    if (!loggedIn && requiredDashboard) {
      window.location.href = loginUrlFor(currentPathWithSearch());
      return;
    }
    if (loggedIn && requiredDashboard && !canView(user, requiredDashboard)) {
      window.location.href = destinationForUser(user);
    }
  }

  // Links into protected pages go through the login page while signed out.
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    if (!link || hasToken()) return;
    const linkUrl = new URL(link.href, window.location.origin);
    if (linkUrl.origin === window.location.origin && dashboardForPath(linkUrl.pathname)) {
      event.preventDefault();
      window.location.href = loginUrlFor(linkUrl.pathname + linkUrl.search);
    }
  });

  window.addEventListener("storage", updateAuthUi);
  window.addEventListener("maintenance-auth-changed", updateAuthUi);
  document.addEventListener("DOMContentLoaded", ensureAuthReady);

  window.maintenanceAuth = {
    token: () => window.localStorage.getItem(TOKEN_KEY),
    user: currentUser,
    clearSession,
    logout,
    destinationForUserOrNext,
    refreshUser,
    ensureReady: ensureAuthReady,
    canView: (dashboard) => canView(currentUser(), dashboard),
    canWrite: (dashboard) => canWrite(currentUser(), dashboard),
    employeeAccessLevel: () => employeeAccessLevel(currentUser()),
    canManageEmployees: () => {
      const user = currentUser();
      return canWrite(user, "employees") && employeeAccessLevel(user) === "confidential";
    }
  };
})();
