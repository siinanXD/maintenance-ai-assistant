import { type ReactNode } from "react";

import { useAuthSession } from "../auth/useAuthSession";
import type { MaintenanceUser } from "../auth/session";
import { ShellGlobalSearch } from "./ShellGlobalSearch";
import {
  canViewNavigationLink,
  canViewNavigationSection,
  isActiveNavigationLink,
  SHELL_NAVIGATION_SECTIONS
} from "./ShellNavigationModel";
import type { ShellNavigationCounts, ShellNavigationLink, ShellNavigationProps } from "./shellNavigationTypes";
import { useShellNavigationCounts } from "./useShellNavigationCounts";

/**
 * Render one sidebar navigation link.
 */
function SidebarNavigationLink({
  counts,
  currentPath,
  link,
  user
}: {
  readonly counts: ShellNavigationCounts;
  readonly currentPath: string;
  readonly link: ShellNavigationLink;
  readonly user: MaintenanceUser | null;
}): ReactNode {
  const isActive = isActiveNavigationLink(link, currentPath);
  const className = [
    "nav-link",
    link.variant === "admin" ? "is-admin-link" : "",
    isActive ? "is-active" : ""
  ].filter(Boolean).join(" ");

  return (
    <a
      aria-current={isActive ? "page" : undefined}
      className={className}
      hidden={!canViewNavigationLink(link, user)}
      href={link.href}
    >
      {link.iconId ? (
        <svg className="nav-icon" aria-hidden="true">
          <use href={`#${link.iconId}`} />
        </svg>
      ) : null}
      <span>{link.label}</span>
      {link.dashboardKey === "errors" ? (
        <span className="nav-count is-alert">
          {counts.errors}
        </span>
      ) : null}
      {link.dashboardKey === "tasks" ? (
        <span className="nav-count">
          {counts.tasks}
        </span>
      ) : null}
    </a>
  );
}

/**
 * Render one mobile navigation link with the same permission hooks as the template.
 */
function MobileNavigationLink({
  currentPath,
  link,
  user
}: {
  readonly currentPath: string;
  readonly link: ShellNavigationLink;
  readonly user: MaintenanceUser | null;
}): ReactNode {
  const isActive = isActiveNavigationLink(link, currentPath);
  const className = [
    "top-nav-link",
    link.variant === "admin" ? "is-admin-link" : "",
    isActive ? "is-active" : ""
  ].filter(Boolean).join(" ");

  return (
    <a
      aria-current={isActive ? "page" : undefined}
      className={className}
      hidden={!canViewNavigationLink(link, user)}
      href={link.href}
    >
      {link.label}
    </a>
  );
}

/**
 * Render the desktop sidebar navigation prepared for the final React shell.
 */
export function ShellSidebarNavigation({
  collapsed = false,
  currentPath,
  onToggleCollapsed
}: ShellNavigationProps): ReactNode {
  const { user } = useAuthSession();
  const counts = useShellNavigationCounts(user);
  const toggleLabel = collapsed ? "Menü erweitern" : "Menü minimieren";

  return (
    <aside className="app-sidebar hidden lg:flex lg:min-h-screen lg:flex-col">
      <a className="sidebar-brand" href="/">
        <span className="sidebar-brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" role="img">
            <path d="M19.4 13.5c.1-.5.1-1 .1-1.5s0-1-.1-1.5l2-1.5-2-3.4-2.4 1a8.2 8.2 0 0 0-2.6-1.5L14 2.5h-4l-.4 2.6A8.2 8.2 0 0 0 7 6.6l-2.4-1-2 3.4 2 1.5c-.1.5-.1 1-.1 1.5s0 1 .1 1.5l-2 1.5 2 3.4 2.4-1a8.2 8.2 0 0 0 2.6 1.5l.4 2.6h4l.4-2.6a8.2 8.2 0 0 0 2.6-1.5l2.4 1 2-3.4-2-1.5ZM12 15.5A3.5 3.5 0 1 1 12 8a3.5 3.5 0 0 1 0 7.5Z" />
          </svg>
        </span>
        <span>
          <span className="sidebar-brand-title">Maintenance</span>
          <span className="sidebar-brand-title">Assistant</span>
        </span>
      </a>
      <nav aria-label="Hauptnavigation" className="sidebar-nav">
        {SHELL_NAVIGATION_SECTIONS.map((section) => (
          <section
            className="sidebar-nav-group"
            hidden={!canViewNavigationSection(section, user)}
            key={section.title}
          >
            <h2>{section.title}</h2>
            {section.links.map((link) => (
              <SidebarNavigationLink
                counts={counts}
                currentPath={currentPath}
                key={link.href}
                link={link}
                user={user}
              />
            ))}
          </section>
        ))}
      </nav>
      <button
        className="sidebar-minimize"
        type="button"
        aria-label={toggleLabel}
        aria-pressed={collapsed}
        data-sidebar-toggle
        onClick={onToggleCollapsed}
      >
        <span className="sidebar-minimize-icon" aria-hidden="true" />
        <span data-sidebar-toggle-label>{toggleLabel}</span>
      </button>
    </aside>
  );
}

/**
 * Render the mobile navigation prepared for the final React shell.
 */
export function ShellMobileNavigation({ currentPath }: ShellNavigationProps): ReactNode {
  const { user } = useAuthSession();

  return (
    <details className="mobile-nav">
      <summary>Menü</summary>
      <div className="mobile-nav-panel">
        <ShellGlobalSearch inputId="global-search-mobile-react" isMobile />
        {SHELL_NAVIGATION_SECTIONS.map((section) => (
          <section
            className="mobile-nav-group"
            hidden={!canViewNavigationSection(section, user)}
            key={section.title}
          >
            <h2>{section.title}</h2>
            {section.links.map((link) => (
              <MobileNavigationLink currentPath={currentPath} key={link.href} link={link} user={user} />
            ))}
          </section>
        ))}
      </div>
    </details>
  );
}
