import { useEffect, useId, type ReactNode } from "react";

import type { CreateActionDefinition } from "./createActionSchema";

type ActionDrawerProps = {
  readonly children: ReactNode;
  readonly description?: string;
  readonly definition?: CreateActionDefinition;
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly title?: string;
};

/**
 * Render a reusable right-side action drawer for create and upload workflows.
 */
export function ActionDrawer({
  children,
  description = "",
  definition,
  isOpen,
  onClose,
  title
}: ActionDrawerProps): ReactNode {
  const drawerTitle = title ?? definition?.title ?? "";
  const drawerDescription = description || definition?.description || "";
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    if (!isOpen) return;

    /**
     * Close the drawer when the user presses Escape.
     */
    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        onClose();
      }
    }

    document.body.classList.add("has-action-drawer");
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.classList.remove("has-action-drawer");
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  return (
    <div className="action-drawer-layer" role="presentation">
      <button
        aria-label="Aktionsbereich schließen"
        className="action-drawer-backdrop"
        onClick={onClose}
        type="button"
      />
      <aside
        aria-describedby={drawerDescription ? descriptionId : undefined}
        aria-labelledby={titleId}
        aria-modal="true"
        className="action-drawer"
        data-action-drawer-key={definition?.key}
        role="dialog"
      >
        <header className="action-drawer-header">
          <div>
            <h2 id={titleId}>{drawerTitle}</h2>
            {drawerDescription ? <p id={descriptionId}>{drawerDescription}</p> : null}
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose} type="button">
            Schließen
          </button>
        </header>
        <div className="action-drawer-body">
          {children}
        </div>
      </aside>
    </div>
  );
}
