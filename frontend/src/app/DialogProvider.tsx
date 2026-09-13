import { createContext, useMemo, type ReactNode } from "react";

import {
  confirmLegacyAction,
  requestLegacyText,
  showLegacyInfoDialog,
  type MaintenanceDialogOptions
} from "./runtimeBridge";

type DialogProviderValue = {
  readonly confirmAction: (options: MaintenanceDialogOptions) => Promise<boolean>;
  readonly requestText: (options: MaintenanceDialogOptions) => Promise<string | null>;
  readonly showInfoDialog: (options: MaintenanceDialogOptions) => Promise<boolean>;
};

const DialogContext = createContext<DialogProviderValue | null>(null);

/**
 * Provide global dialog helpers through React while preserving legacy dialogs.
 */
export function DialogProvider({ children }: { readonly children: ReactNode }): ReactNode {
  const value = useMemo<DialogProviderValue>(() => ({
    confirmAction: confirmLegacyAction,
    requestText: requestLegacyText,
    showInfoDialog: showLegacyInfoDialog
  }), []);

  return <DialogContext.Provider value={value}>{children}</DialogContext.Provider>;
}

