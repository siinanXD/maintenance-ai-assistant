(function () {
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
  function featureRoutes(feature) {
    return [feature.route].concat(Array.isArray(feature.routeAliases) ? feature.routeAliases : []);
  }

  const DASHBOARD_PATHS = Object.fromEntries(
    featureRegistry.all.flatMap((feature) => (
      featureRoutes(feature).map((route) => [route, feature.key])
    ))
  );
  const DASHBOARD_DESTINATIONS = Object.fromEntries(
    featureRegistry.all.map((feature) => [feature.key, feature.route])
  );
  const DASHBOARD_ORDER = featureRegistry.all.map((feature) => feature.key);

  function permissionDashboard(featureOrDashboard) {
    return featureRegistry.permissionKeyFor
      ? featureRegistry.permissionKeyFor(featureOrDashboard)
      : featureOrDashboard;
  }

  function permissionFor(user, dashboard) {
    if (isAdminUser(user)) return { can_view: true, can_write: true, employee_access_level: "confidential" };
    const permissionKey = permissionDashboard(dashboard);
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
    const exactDashboard = DASHBOARD_PATHS[pathname];
    if (exactDashboard) return exactDashboard;
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

  function displayName(user) {
    if (!user) return "Benutzer";
    const source = user.username || user.email || "Eingeloggt";
    return source.includes("@") ? source.split("@")[0] : source;
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

  async function revokeAuthToken(authToken) {
    if (!authToken) return;
    const response = await fetch("/api/v1/auth/logout", {
      method: "POST",
      headers: { "Authorization": "Bearer " + authToken },
      keepalive: true
    });
    if (!response.ok && response.status !== 401 && response.status !== 422) {
      throw new Error("Logout failed with status " + response.status);
    }
  }

  async function logout() {
    const authToken = window.localStorage.getItem(TOKEN_KEY);
    try {
      await revokeAuthToken(authToken);
    } catch (error) {
      console.warn("Logout token revocation failed.", error);
    } finally {
      clearSession({ redirect: true });
    }
  }

  function highContrastEnabled() {
    return window.localStorage.getItem(CONTRAST_KEY) === "true";
  }

  function applyContrastPreference() {
    const enabled = highContrastEnabled();
    document.documentElement.classList.toggle("high-contrast", enabled);
    document.body.classList.toggle("high-contrast", enabled);
    document.querySelectorAll("[data-contrast-toggle]").forEach((button) => {
      button.setAttribute("aria-pressed", String(enabled));
      button.textContent = enabled ? "Standard-Kontrast" : "Hoher Kontrast";
    });
  }

  let authReadyPromise;
  let refreshInFlight;

  function refreshUserInBackground() {
    if (!refreshInFlight) {
      refreshInFlight = refreshUser().finally(() => {
        refreshInFlight = null;
      });
    }
    return refreshInFlight;
  }

  async function ensureAuthReady() {
    if (!authReadyPromise) {
      authReadyPromise = (async () => {
        updateAuthUi();
        if (hasToken()) {
          refreshUserInBackground();
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
    const isAdmin = isAdminUser(user);
    document.body.classList.toggle("is-authenticated", loggedIn);
    document.body.classList.toggle("is-admin", isAdmin);
    applyContrastPreference();

    document.querySelectorAll("[data-auth-session]").forEach((element) => {
      element.hidden = !loggedIn;
    });

    document.querySelectorAll("[data-session-name]").forEach((element) => {
      element.textContent = displayName(user);
    });

    document.querySelectorAll("[data-auth-login-link]").forEach((element) => {
      element.hidden = loggedIn;
    });

    // The React topbar (ShellTopbar.tsx) owns the notification badge on every shell page.
    // Fetching here as well sent the same request two extra times per page view.
    const reactOwnsNotifications = Boolean(document.getElementById("maintenance-shell-topbar-root"));
    if (loggedIn && !reactOwnsNotifications) {
      refreshNotificationBadge();
    } else if (!loggedIn) {
      updateNotificationBadge(0);
    }

    document.querySelectorAll("[data-feature-key], [data-dashboard-nav]").forEach((element) => {
      const featureKey = element.dataset.featureKey || element.dataset.dashboardNav;
      element.hidden = !loggedIn || !canView(user, featureKey);
    });

    document.querySelectorAll("[data-nav-group]").forEach((group) => {
      const visibleLinks = group.querySelectorAll("[data-dashboard-nav]:not([hidden])");
      group.hidden = visibleLinks.length === 0;
    });

    document.querySelectorAll("[data-nav-root]").forEach((root) => {
      const visibleGroups = root.querySelectorAll("[data-nav-group]:not([hidden])");
      root.hidden = visibleGroups.length === 0;
    });

    document.querySelectorAll("[data-permission-view]").forEach((element) => {
      element.hidden = !canView(user, element.dataset.permissionView);
    });

    document.querySelectorAll("[data-permission-write]").forEach((element) => {
      element.hidden = !canWrite(user, element.dataset.permissionWrite);
    });

    document.querySelectorAll("[data-hr-only]").forEach((element) => {
      element.hidden = !isAdmin;
    });

    document.querySelectorAll("[data-login-form]").forEach((element) => {
      element.hidden = loggedIn;
    });

    document.querySelectorAll("[data-logged-in-panel]").forEach((element) => {
      element.hidden = !loggedIn;
    });

    const requiredDashboard = dashboardForPath(window.location.pathname);
    if (!loggedIn && requiredDashboard) {
      window.location.href = loginUrlFor(currentPathWithSearch());
      return;
    }
    if (loggedIn && requiredDashboard && !canView(user, requiredDashboard)) {
      window.location.href = destinationForUser(user);
    }
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-logout-button]");
    if (button) {
      logout();
    }

    const contrastButton = event.target.closest("[data-contrast-toggle]");
    if (contrastButton) {
      window.localStorage.setItem(CONTRAST_KEY, String(!highContrastEnabled()));
      applyContrastPreference();
    }

    const notificationButton = event.target.closest("[data-topbar-notifications]");
    if (notificationButton && hasToken()) {
      markNotificationsRead();
    }

    const link = event.target.closest("a[href]");
    if (link && !hasToken()) {
      const linkUrl = new URL(link.href, window.location.origin);
      const dashboard = dashboardForPath(linkUrl.pathname);
      if (linkUrl.origin === window.location.origin && dashboard) {
        event.preventDefault();
        window.location.href = loginUrlFor(linkUrl.pathname + linkUrl.search);
      }
    }
  });

  let notificationsInFlight;

  function updateNotificationBadge(count) {
    document.querySelectorAll("[data-notification-badge]").forEach((badge) => {
      const unreadCount = Number(count || 0);
      badge.textContent = String(unreadCount);
      badge.hidden = unreadCount <= 0;
    });
  }

  async function refreshNotificationBadge() {
    if (notificationsInFlight) return notificationsInFlight;
    const authToken = window.localStorage.getItem(TOKEN_KEY);
    if (!authToken) {
      updateNotificationBadge(0);
      return null;
    }
    notificationsInFlight = fetch("/api/v1/notifications?limit=5", {
      headers: { "Authorization": "Bearer " + authToken }
    })
      .then((response) => response.ok ? response.json() : null)
      .then((payload) => {
        const data = payload && payload.success ? payload.data : payload;
        updateNotificationBadge(data && data.unread_count);
        return data;
      })
      .catch(() => {
        updateNotificationBadge(0);
        return null;
      })
      .finally(() => {
        notificationsInFlight = null;
      });
    return notificationsInFlight;
  }

  async function markNotificationsRead() {
    const authToken = window.localStorage.getItem(TOKEN_KEY);
    if (!authToken) return;
    try {
      await fetch("/api/v1/notifications/read-all", {
        method: "PATCH",
        headers: { "Authorization": "Bearer " + authToken }
      });
      updateNotificationBadge(0);
    } catch (error) {
      refreshNotificationBadge();
    }
  }

  window.addEventListener("storage", () => {
    updateAuthUi();
    applyContrastPreference();
  });
  window.addEventListener("maintenance-auth-changed", updateAuthUi);
  document.addEventListener("DOMContentLoaded", ensureAuthReady);

  window.maintenanceAuth = {
    token: () => window.localStorage.getItem(TOKEN_KEY),
    user: currentUser,
    clearSession,
    destinationForUser,
    destinationForUserOrNext,
    refreshUser,
    refreshUserInBackground,
    refreshNotificationBadge,
    ensureReady: ensureAuthReady,
    isAdmin: () => isAdminUser(currentUser()),
    canView: (dashboard) => canView(currentUser(), dashboard),
    canWrite: (dashboard) => canWrite(currentUser(), dashboard),
    employeeAccessLevel: () => employeeAccessLevel(currentUser()),
    canManageEmployees: () => {
      const user = currentUser();
      return canWrite(user, "employees") && employeeAccessLevel(user) === "confidential";
    }
  };
})();
