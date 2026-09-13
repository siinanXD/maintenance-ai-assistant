import type { MaintenanceAuthRuntime } from "../auth/permissions";

/**
 * Typed access to the globals that the plain scripts in base.html publish:
 * auth.js (window.maintenanceAuth), core/action-dialogs.js (window.maintenanceDialogs)
 * and app.js (window.maintenanceFrontend).
 */

type MaintenanceDialogOptions = {
  readonly cancelText?: string;
  readonly confirmText?: string;
  readonly defaultValue?: string;
  readonly inputType?: string;
  readonly label?: string;
  readonly message?: string;
  readonly multiline?: boolean;
  readonly required?: boolean;
  readonly requiredMessage?: string;
  readonly title?: string;
};

type MaintenanceDialogsRuntime = {
  readonly confirmAction?: (options: MaintenanceDialogOptions) => Promise<boolean>;
  readonly requestText?: (options: MaintenanceDialogOptions) => Promise<string | null>;
};

type ToastOptions = string | { readonly variant?: string; readonly duration?: number };

type MaintenanceFrontendRuntime = {
  readonly showInterfaceToast?: (message: string, options?: ToastOptions) => void;
};

declare global {
  interface Window {
    readonly maintenanceAuth?: MaintenanceAuthRuntime;
    readonly maintenanceDialogs?: MaintenanceDialogsRuntime;
    readonly maintenanceFrontend?: MaintenanceFrontendRuntime;
  }
}

/**
 * Return the auth runtime once auth.js has initialized it.
 */
export function authRuntime(): MaintenanceAuthRuntime | null {
  return window.maintenanceAuth || null;
}

/**
 * Show a toast through app.js.
 */
export function showToast(message: string, options?: ToastOptions): void {
  window.maintenanceFrontend?.showInterfaceToast?.(message, options);
}

/**
 * Open the shared confirmation dialog, falling back to the browser dialog.
 */
export function confirmAction(options: MaintenanceDialogOptions): Promise<boolean> {
  if (window.maintenanceDialogs?.confirmAction) {
    return window.maintenanceDialogs.confirmAction(options);
  }
  return Promise.resolve(window.confirm(options.message || options.title || "Aktion bestätigen?"));
}

/**
 * Open the shared text input dialog.
 */
export function requestText(options: MaintenanceDialogOptions): Promise<string | null> {
  if (window.maintenanceDialogs?.requestText) {
    return window.maintenanceDialogs.requestText(options);
  }
  showToast("Eingabedialog konnte nicht geöffnet werden.", "error");
  return Promise.resolve(null);
}
