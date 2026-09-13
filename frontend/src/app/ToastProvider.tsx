import { createContext, useMemo, type ReactNode } from "react";

import { setLegacyWorkflowStatus, showLegacyToast } from "./runtimeBridge";

type ToastProviderValue = {
  readonly setWorkflowStatus: (message: string, variant?: string) => void;
  readonly showToast: (message: string, options?: string | { readonly variant?: string; readonly duration?: number }) => void;
};

const ToastContext = createContext<ToastProviderValue | null>(null);

/**
 * Provide global toast and workflow-status helpers through React.
 */
export function ToastProvider({ children }: { readonly children: ReactNode }): ReactNode {
  const value = useMemo<ToastProviderValue>(() => ({
    setWorkflowStatus: setLegacyWorkflowStatus,
    showToast: showLegacyToast
  }), []);

  return <ToastContext.Provider value={value}>{children}</ToastContext.Provider>;
}

