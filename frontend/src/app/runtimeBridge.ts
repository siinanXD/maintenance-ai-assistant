import type { MaintenanceAuthRuntime } from "../auth/permissions";

type MaintenanceFeature = {
  readonly key: string;
  readonly label?: string;
  readonly permissionKey?: string;
  readonly route: string;
  readonly routeAliases?: readonly string[];
  readonly routePrefixes?: readonly string[];
};

export type MaintenanceFeatureRegistry = {
  readonly all: readonly MaintenanceFeature[];
  readonly destinations?: Record<string, string>;
  readonly forPath?: (pathname: string) => MaintenanceFeature | null;
  readonly get?: (featureKey: string) => MaintenanceFeature | null;
  readonly keys?: readonly string[];
  readonly permissionKeyFor?: (featureKey: string) => string;
};

export type MaintenanceDialogOptions = {
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
  readonly showInfoDialog?: (options: MaintenanceDialogOptions) => Promise<boolean>;
};

type MaintenanceFrontendRuntime = {
  readonly setWorkflowStatus?: (message: string, variant?: string) => void;
  readonly showInterfaceToast?: (message: string, options?: string | { readonly variant?: string; readonly duration?: number }) => void;
};

declare global {
  interface Window {
    readonly maintenanceAuth?: MaintenanceAuthRuntime;
    readonly maintenanceDialogs?: MaintenanceDialogsRuntime;
    readonly maintenanceFeatures?: MaintenanceFeatureRegistry;
    readonly maintenanceFrontend?: MaintenanceFrontendRuntime;
  }
}

/**
 * Return the legacy auth runtime when auth.js has initialized it.
 */
export function legacyAuthRuntime(): MaintenanceAuthRuntime | null {
  return window.maintenanceAuth || null;
}

/**
 * Return the legacy feature registry with a stable empty fallback.
 */
export function legacyFeatureRegistry(): MaintenanceFeatureRegistry {
  return window.maintenanceFeatures || { all: [] };
}

/**
 * Return a permission key from the legacy feature registry when available.
 */
export function legacyPermissionKeyFor(featureKey: string): string {
  return legacyFeatureRegistry().permissionKeyFor?.(featureKey) || featureKey;
}

/**
 * Show a toast through the existing global frontend runtime.
 */
export function showLegacyToast(
  message: string,
  options?: string | { readonly variant?: string; readonly duration?: number }
): void {
  if (window.maintenanceFrontend?.showInterfaceToast) {
    window.maintenanceFrontend.showInterfaceToast(message, options);
  }
}

/**
 * Set the shared workflow status through the existing global frontend runtime.
 */
export function setLegacyWorkflowStatus(message: string, variant?: string): void {
  if (window.maintenanceFrontend?.setWorkflowStatus) {
    window.maintenanceFrontend.setWorkflowStatus(message, variant);
  }
}

/**
 * Open the legacy confirmation dialog with a browser-confirm fallback.
 */
export function confirmLegacyAction(options: MaintenanceDialogOptions): Promise<boolean> {
  if (window.maintenanceDialogs?.confirmAction) {
    return window.maintenanceDialogs.confirmAction(options);
  }
  return Promise.resolve(window.confirm(options.message || options.title || "Aktion bestätigen?"));
}

/**
 * Open the legacy text dialog with a browser-prompt fallback.
 */
export function requestLegacyText(options: MaintenanceDialogOptions): Promise<string | null> {
  if (window.maintenanceDialogs?.requestText) {
    return window.maintenanceDialogs.requestText(options);
  }
  console.warn("maintenanceDialogs.requestText is unavailable", options);
  showLegacyToast("Eingabedialog konnte nicht geöffnet werden.", "error");
  return Promise.resolve(null);
}

/**
 * Open the legacy info dialog with an alert fallback.
 */
export function showLegacyInfoDialog(options: MaintenanceDialogOptions): Promise<boolean> {
  if (window.maintenanceDialogs?.showInfoDialog) {
    return window.maintenanceDialogs.showInfoDialog(options);
  }
  console.warn("maintenanceDialogs.showInfoDialog is unavailable", options);
  showLegacyToast(options.message || options.title || "Information", "info");
  return Promise.resolve(true);
}
