import { useEffect, useRef, type ReactNode } from "react";

import { authRuntime, showToast } from "../app/runtimeBridge";
import { useAuthSession } from "../auth/useAuthSession";
import { currentPathWithSearch, displayStoredUserName, loginUrlForPath } from "../auth/session";
import { userInitials, userRoleLabel } from "../auth/userLabels";
import { ShellGlobalSearch } from "./ShellGlobalSearch";
import { ShellMobileNavigation } from "./ShellNavigation";
import { useHighContrastPreference, useNotificationBadge, useShellShiftState } from "./shellTopbarState";

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
  const session = useAuthSession();
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
   * Open the briefing on the cockpit and mark notifications as read.
   */
  function handleNotificationClick(): void {
    if (isLoggedIn) {
      void markNotificationsRead();
    }

    const briefing = document.querySelector("#daily-briefing");
    if (briefing) {
      briefing.scrollIntoView({ behavior: "smooth", block: "start" });
      showToast("Briefing und kritische Hinweise geöffnet.");
      return;
    }

    if (window.location.pathname !== "/") {
      window.location.href = "/";
    }
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
          <a
            className={`topbar-select shift-select is-${shiftState.key}`}
            href="/shiftplans"
            aria-label={`Aktuell laufende Schicht: ${shiftState.label}, ${shiftState.dateValue}`}
            title={`${shiftState.dateTitle}, ${shiftState.time} – zum Schichtplan`}
          >
            <span className="status-dot" aria-hidden="true" />
            <span>
              <strong>{shiftState.label}</strong>
              <small>
                <span title={shiftState.dateTitle}>{shiftState.dateValue}</span>
                {" · "}
                <span>{shiftState.time}</span>
              </small>
            </span>
          </a>
          <button
            className="notification-button"
            type="button"
            aria-label={
              unreadNotifications > 0 ? `${unreadNotifications} ungelesene Benachrichtigungen` : "Benachrichtigungen"
            }
            title="Briefing und kritische Hinweise öffnen"
            onClick={handleNotificationClick}
          >
            <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 22a2.3 2.3 0 0 0 2.2-1.6H9.8A2.3 2.3 0 0 0 12 22Zm7-5-1.7-2.2V10a5.4 5.4 0 0 0-4.1-5.3V3a1.2 1.2 0 1 0-2.4 0v1.7A5.4 5.4 0 0 0 6.7 10v4.8L5 17v1.2h14V17Z" /></svg>
            <span className="notification-badge" hidden={unreadNotifications <= 0}>
              {unreadNotifications > 99 ? "99+" : unreadNotifications}
            </span>
          </button>
          <details className="user-menu" hidden={!isLoggedIn} ref={userMenuRef}>
            <summary className="user-menu-trigger" aria-label={`Benutzermenü für ${sessionName}`}>
              <span className="user-avatar" aria-hidden="true">{userInitials(sessionName)}</span>
              <span className="user-menu-identity">
                <strong>{sessionName}</strong>
                <small>{userRoleLabel(session.user)}</small>
              </span>
            </summary>
            <div className="user-menu-panel" role="menu">
              <button
                className="user-menu-item"
                type="button"
                role="menuitemcheckbox"
                aria-checked={highContrastEnabled}
                onClick={toggleHighContrast}
              >
                {highContrastEnabled ? "Standard-Kontrast" : "Hoher Kontrast"}
              </button>
              <button
                className="user-menu-item is-danger"
                type="button"
                role="menuitem"
                onClick={() => void authRuntime()?.logout?.()}
              >
                Abmelden
              </button>
            </div>
          </details>
          <a className={loginClassName} href={loginHref} hidden={isLoggedIn}>Anmelden</a>
        </div>
      </div>
    </header>
  );
}
