import { StrictMode, useEffect, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { createPortal } from "react-dom";

import { ShellChatWidget } from "./ShellChatWidget";
import { ShellIconSprite } from "./ShellIconSprite";
import { ShellSidebarNavigation } from "./ShellNavigation";

import { ShellTopbar } from "./ShellTopbar";
import { readSidebarCollapsedPreference, writeSidebarCollapsedPreference } from "./shellPreferences";

const SHELL_RUNTIME_ROOT_ID = "maintenance-shell-runtime-root";

type ShellPortalTarget = {
  readonly fallbackSelector?: string;
  readonly rootId: string;
};

const SHELL_TARGETS: readonly ShellPortalTarget[] = [
  {
    fallbackSelector: "[data-react-shell-sidebar-fallback]",
    rootId: "maintenance-shell-sidebar-root"
  },
  {
    fallbackSelector: "[data-react-shell-topbar-fallback]",
    rootId: "maintenance-shell-topbar-root"
  },
  {
    fallbackSelector: "[data-react-shell-chat-fallback]",
    rootId: "maintenance-shell-chat-root"
  },
  {
    rootId: "maintenance-shell-icons-root"
  }
] as const;

/**
 * Return the current route path for shell active states.
 */
function currentPath(): string {
  return window.location.pathname;
}

/**
 * Return the page title from the fallback header when available.
 */
function currentHeaderTitle(): string {
  const topbarRoot = document.getElementById("maintenance-shell-topbar-root");
  return topbarRoot?.dataset.shellTitle?.trim() || "Maintenance Assistant";
}

/**
 * Return a shell portal target by element id.
 */
function targetElement(rootId: string): HTMLElement | null {
  return document.getElementById(rootId);
}

/**
 * Reveal one React shell target and hide its matching Jinja fallback.
 */
function revealShellTarget(target: ShellPortalTarget): void {
  const rootElement = targetElement(target.rootId);
  if (!rootElement) return;

  rootElement.hidden = false;
  rootElement.dataset.reactMounted = "true";
  if (target.fallbackSelector) {
    document.querySelectorAll<HTMLElement>(target.fallbackSelector).forEach((element) => {
      element.hidden = true;
      element.dataset.reactFallbackHidden = "true";
    });
  }
}

/**
 * Render the global React sidebar while preserving the existing page content.
 */
function ShellSidebarChrome(): ReactNode {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(readSidebarCollapsedPreference);

  useEffect(() => {
    document.querySelector(".app-shell-layout")?.classList.toggle(
      "is-sidebar-collapsed",
      isSidebarCollapsed
    );
  }, [isSidebarCollapsed]);

  /**
   * Toggle and persist the global React sidebar state.
   */
  function toggleSidebarCollapsed(): void {
    setIsSidebarCollapsed((currentValue) => {
      const nextValue = !currentValue;
      writeSidebarCollapsedPreference(nextValue);
      return nextValue;
    });
  }

  return (
    <ShellSidebarNavigation
      collapsed={isSidebarCollapsed}
      currentPath={currentPath()}
      onToggleCollapsed={toggleSidebarCollapsed}
    />
  );
}

/**
 * Render all shell pieces through one provider tree and portal them into base.html placeholders.
 */
function ShellChromeRuntime(): ReactNode {
  const iconsRoot = targetElement("maintenance-shell-icons-root");
  const sidebarRoot = targetElement("maintenance-shell-sidebar-root");
  const topbarRoot = targetElement("maintenance-shell-topbar-root");
  const chatRoot = targetElement("maintenance-shell-chat-root");

  useEffect(() => {
    SHELL_TARGETS.forEach(revealShellTarget);
  }, []);

  return (
    <>
      {iconsRoot ? createPortal(<ShellIconSprite />, iconsRoot) : null}
      {sidebarRoot ? createPortal(<ShellSidebarChrome />, sidebarRoot) : null}
      {topbarRoot ? createPortal(<ShellTopbar currentPath={currentPath()} title={currentHeaderTitle()} />, topbarRoot) : null}
      {chatRoot ? createPortal(<ShellChatWidget />, chatRoot) : null}
    </>
  );
}

/**
 * Mount the central React shell runtime once per page.
 */
function bootstrapShellChrome(): void {
  const rootElement = document.getElementById(SHELL_RUNTIME_ROOT_ID);
  if (!rootElement || rootElement.dataset.reactMounted === "true") return;

  createRoot(rootElement).render(
    <StrictMode>
      <ShellChromeRuntime />
    </StrictMode>
  );
  rootElement.dataset.reactMounted = "true";
}

bootstrapShellChrome();
