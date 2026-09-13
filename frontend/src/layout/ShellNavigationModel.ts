import { canViewStoredDashboard } from "../auth/permissions";
import type { MaintenanceUser } from "../auth/session";
import type { ShellNavigationLink, ShellNavigationSection } from "./ShellNavigationTypes";

export const SHELL_NAVIGATION_SECTIONS: readonly ShellNavigationSection[] = [
  {
    defaultOpen: true,
    title: "Cockpit",
    links: [{ dashboardKey: "dashboard", href: "/", iconId: "icon-dashboard", label: "Cockpit" }]
  },
  {
    defaultOpen: true,
    title: "Arbeit",
    links: [
      { dashboardKey: "errors", href: "/errors", iconId: "icon-alert", label: "Störungen" },
      { dashboardKey: "tasks", href: "/tasks", iconId: "icon-tasks", label: "Aufgaben" },
      {
        dashboardKey: "machines",
        featureKey: "maintenance",
        href: "/maintenance",
        iconId: "icon-inspection",
        label: "Prüfungen & Wartung"
      },
      {
        dashboardKey: "shiftplans",
        featureKey: "handover",
        href: "/handover",
        iconId: "icon-handover",
        label: "Schichtübergabe",
        permissionKey: "shiftplans"
      }
    ]
  },
  {
    title: "Wissen & Anlagen",
    links: [
      {
        dashboardKey: "machines",
        href: "/machines",
        iconId: "icon-machine",
        label: "Maschinen",
        routePrefix: "/machines"
      },
      { dashboardKey: "inventory", href: "/inventory", iconId: "icon-inventory", label: "Inventar" },
      { dashboardKey: "documents", href: "/documents", iconId: "icon-document", label: "Dokumente" }
    ]
  },
  {
    title: "Planung & Personal",
    links: [
      { dashboardKey: "shiftplans", href: "/shiftplans", iconId: "icon-calendar", label: "Schichtpläne" },
      {
        dashboardKey: "employees",
        featureKey: "vacations",
        href: "/vacations",
        iconId: "icon-vacation",
        label: "Urlaube",
        permissionKey: "employees"
      },
      { dashboardKey: "employees", href: "/employees", iconId: "icon-users", label: "Mitarbeiter" }
    ]
  },
  {
    title: "Administration",
    links: [
      {
        dashboardKey: "admin_users",
        href: "/admin/users",
        iconId: "icon-admin",
        label: "Benutzer",
        variant: "admin"
      },
      {
        dashboardKey: "admin_users",
        featureKey: "admin_ai",
        href: "/admin/ai",
        iconId: "icon-ai",
        label: "KI-Administration",
        permissionKey: "admin_ai",
        routePrefix: "/admin/ai",
        variant: "admin"
      }
    ]
  }
] as const;

/**
 * Return whether a navigation link represents the current path.
 */
export function isActiveNavigationLink(link: ShellNavigationLink, currentPath: string): boolean {
  if (link.routePrefix) {
    return currentPath === link.href || currentPath.startsWith(link.routePrefix + "/");
  }
  return currentPath === link.href;
}

/**
 * Return whether the current session may see a shell navigation link.
 */
export function canViewNavigationLink(link: ShellNavigationLink, user: MaintenanceUser | null): boolean {
  return Boolean(user) && canViewStoredDashboard(user, link.permissionKey ?? link.dashboardKey);
}

/**
 * Return whether the current session may see any link in a navigation section.
 */
export function canViewNavigationSection(section: ShellNavigationSection, user: MaintenanceUser | null): boolean {
  return section.links.some((link) => canViewNavigationLink(link, user));
}

/**
 * Build the shared navigation attributes used by permissions and active-state code.
 */
export function navigationDataAttributes(link: ShellNavigationLink): Record<string, string> {
  return {
    "data-dashboard-nav": link.dashboardKey,
    ...(link.featureKey ? { "data-feature-key": link.featureKey } : {})
  };
}
