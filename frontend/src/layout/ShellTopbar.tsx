import { useEffect, useRef, type MouseEvent, type ReactNode } from "react";

import { legacyAuthRuntime, showLegacyToast } from "../app/runtimeBridge";
import { useAuthContext } from "../auth/AuthProvider";
import { currentPathWithSearch, displayStoredUserName, loginUrlForPath } from "../auth/session";
import { userInitials, userRoleLabel } from "../auth/userLabels";
import { ShellGlobalSearch } from "./ShellGlobalSearch";
import { ShellMobileNavigation } from "./ShellNavigation";
import { useHighContrastPreference, useNotificationBadge, useShellShiftState } from "./ShellTopbarState";

type ShellTopbarProps = {
  readonly currentPath: string;
  readonly title: string;
};

/**
 * Render the topbar and global search hooks for the React shell.
 *
 * One row at desktop widths: title, search, the current shift with date, notifications
 * and a compact user menu. Contrast and logout live inside the user menu instead of
 * taking two permanent buttons in the bar.
 */
export function ShellTopbar({ currentPath, title }: ShellTopbarProps): ReactNode {
  const loginClassName = currentPath === "/login" ? "btn btn-primary btn-sm btn-active" : "btn btn-primary btn-sm";
  const session = useAuthContext();
  const shiftState = useShellShiftState();
  const [highContrastEnabled, toggleHighContrast] = useHighContrastPreference();
  const isLoggedIn = Boolean(session.token);
  const [unreadNotifications, markNotificationsRead] = useNotificationBadge(isLoggedIn);
  const sessionName = displayStoredUserName(session.user);
  const loginHref = currentPath === "/login" ? "/login" : loginUrlForPath(currentPathWithSearch());
  const userMenuRef = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    /**
     * Close the user menu when a click lands outside of it.
     */
    function closeOnOutsideClick(event: globalThis.MouseEvent): void {
      const menu = userMenuRef.current;
      if (menu?.open && event.target instanceof Node && !menu.contains(event.target)) {
        menu.open = false;
      }
    }

    document.addEventListener("click", closeOnOutsideClick);
    return () => document.removeEventListener("click", closeOnOutsideClick);
  }, []);

  /**
   * Delegate logout to the existing auth runtime while preserving a fallback path.
   */
  function handleLogout(event: MouseEvent<HTMLButtonElement>): void {
    event.preventDefault();
    event.stopPropagation();

    const authRuntime = legacyAuthRuntime();
    if (authRuntime?.clearSession) {
      authRuntime.clearSession({ redirect: true });
      return;
    }
    window.localStorage.removeItem("maintenance_access_token");
    window.localStorage.removeItem("maintenance_user");
    window.dispatchEvent(new Event("maintenance-auth-changed"));
    if (window.location.pathname !== "/login") {
      window.location.href = loginUrlForPath(currentPathWithSearch());
    }
  }

  /**
   * Toggle high contrast through React without triggering the legacy delegated handler twice.
   */
  function handleContrastToggle(event: MouseEvent<HTMLButtonElement>): void {
    event.preventDefault();
    event.stopPropagation();
    toggleHighContrast();
  }

  /**
   * Mark topbar notifications read and keep the legacy briefing navigation behavior.
   */
  function handleNotificationClick(event: MouseEvent<HTMLButtonElement>): void {
    event.preventDefault();
    event.stopPropagation();

    if (isLoggedIn) {
      void markNotificationsRead();
    }

    const briefing = document.querySelector("#daily-briefing");
    if (briefing) {
      briefing.scrollIntoView({ behavior: "smooth", block: "start" });
      showLegacyToast("Briefing und kritische Hinweise geöffnet.");
      return;
    }

    if (window.location.pathname !== "/") {
      window.location.href = "/";
    }
  }

  /**
   * Navigate to shift planning from the shift and date control.
   */
  function handleShiftplansClick(event: MouseEvent<HTMLButtonElement>): void {
    event.preventDefault();
    event.stopPropagation();
    window.location.href = "/shiftplans";
  }

  return (
    <header className="app-header">
      <div className="mobile-header lg:hidden">
        <a className="mobile-brand" href="/">
          <span className="sidebar-brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" role="img">
              <path d="M19.4 13.5c.1-.5.1-1 .1-1.5s0-1-.1-1.5l2-1.5-2-3.4-2.4 1a8.2 8.2 0 0 0-2.6-1.5L14 2.5h-4l-.4 2.6A8.2 8.2 0 0 0 7 6.6l-2.4-1-2 3.4 2 1.5c-.1.5-.1 1-.1 1.5s0 1 .1 1.5l-2 1.5 2 3.4 2.4-1a8.2 8.2 0 0 0 2.6 1.5l.4 2.6h4l.4-2.6a8.2 8.2 0 0 0 2.6-1.5l2.4 1 2-3.4-2-1.5ZM12 15.5A3.5 3.5 0 1 1 12 8a3.5 3.5 0 0 1 0 7.5Z" />
            </svg>
          </span>
          <span>Maintenance Assistant</span>
        </a>
        <ShellMobileNavigation currentPath={currentPath} />
      </div>
      <div className="desktop-topbar">
        <div className="topbar-title" aria-label={`Aktuelle Seite: ${title}`}>{title}</div>
        <div className="topbar-actions">
          <ShellGlobalSearch inputId="global-search-desktop-react" />
          <button
            className={`topbar-select shift-select is-${shiftState.key}`}
            type="button"
            aria-label={`Aktuell laufende Schicht: ${shiftState.label}, ${shiftState.dateValue}`}
            title={`${shiftState.dateTitle}, ${shiftState.time} – zum Schichtplan`}
            data-topbar-date
            data-current-shift
            onClick={handleShiftplansClick}
          >
            <span className="status-dot" aria-hidden="true" />
            <span>
              <strong data-current-shift-label>{shiftState.label}</strong>
              <small>
                <span data-current-date title={shiftState.dateTitle}>{shiftState.dateValue}</span>
                {" · "}
                <span data-current-shift-time>{shiftState.time}</span>
              </small>
            </span>
          </button>
          <button
            className="notification-button"
            type="button"
            aria-label={
              unreadNotifications > 0 ? `${unreadNotifications} ungelesene Benachrichtigungen` : "Benachrichtigungen"
            }
            title="Briefing und kritische Hinweise öffnen"
            data-topbar-notifications
            onClick={handleNotificationClick}
          >
            <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 22a2.3 2.3 0 0 0 2.2-1.6H9.8A2.3 2.3 0 0 0 12 22Zm7-5-1.7-2.2V10a5.4 5.4 0 0 0-4.1-5.3V3a1.2 1.2 0 1 0-2.4 0v1.7A5.4 5.4 0 0 0 6.7 10v4.8L5 17v1.2h14V17Z" /></svg>
            <span className="notification-badge" data-notification-badge hidden={unreadNotifications <= 0}>
              {unreadNotifications > 99 ? "99+" : unreadNotifications}
            </span>
          </button>
          <details className="user-menu" data-auth-session hidden={!isLoggedIn} ref={userMenuRef}>
            <summary className="user-menu-trigger" aria-label={`Benutzermenü für ${sessionName}`}>
              <span className="user-avatar" aria-hidden="true">{userInitials(sessionName)}</span>
              <span className="user-menu-identity">
                <strong data-session-name>{sessionName}</strong>
                <small>{userRoleLabel(session.user)}</small>
              </span>
            </summary>
            <div className="user-menu-panel" role="menu">
              <button
                className="user-menu-item"
                type="button"
                role="menuitemcheckbox"
                data-contrast-toggle
                aria-checked={highContrastEnabled}
                onClick={handleContrastToggle}
              >
                {highContrastEnabled ? "Standard-Kontrast" : "Hoher Kontrast"}
              </button>
              <button
                className="user-menu-item is-danger"
                type="button"
                role="menuitem"
                data-logout-button
                onClick={handleLogout}
              >
                Abmelden
              </button>
            </div>
          </details>
          <a data-auth-login-link className={loginClassName} href={loginHref} hidden={isLoggedIn}>Anmelden</a>
        </div>
      </div>
    </header>
  );
}
