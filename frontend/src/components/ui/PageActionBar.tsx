import type { ReactNode } from "react";

import type { CreateActionDefinition } from "./createActionSchema";

export type PageAction = {
  readonly disabled?: boolean;
  readonly hidden?: boolean;
  readonly label?: string;
  readonly onClick?: () => void;
  readonly href?: string;
  readonly schema?: CreateActionDefinition;
  readonly variant?: "primary" | "outline" | "ghost";
};

type PageActionBarProps = {
  readonly actions: readonly PageAction[];
  readonly label: string;
};

/**
 * Render a compact, shared page action bar for primary page commands.
 */
export function PageActionBar({ actions, label }: PageActionBarProps): ReactNode {
  const visibleActions = actions.filter((action) => !action.hidden);

  if (!visibleActions.length) {
    return null;
  }

  return (
    <div className="page-action-bar" aria-label={label}>
      {visibleActions.map((action) => {
        const className = `btn btn-sm btn-${action.variant ?? "outline"}`;
        const actionLabel = action.label ?? action.schema?.primaryLabel ?? action.schema?.title ?? "";
        if (action.href) {
          return (
            <a className={className} href={action.href} key={actionLabel}>
              {actionLabel}
            </a>
          );
        }

        return (
          <button
            className={className}
            disabled={action.disabled}
            key={actionLabel}
            onClick={action.onClick}
            type="button"
          >
            {actionLabel}
          </button>
        );
      })}
    </div>
  );
}
