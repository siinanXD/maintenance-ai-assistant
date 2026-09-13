import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";

import { markIslandMounted } from "../app/islandMount";
import { canWriteDashboard } from "../auth/permissions";
import { hasStoredToken } from "../auth/session";
import { subscribeToSessionChange } from "../auth/sessionChange";
import {
  completeHandover,
  createHandover,
  loadHandoverMachines,
  loadHandovers,
  updateHandover,
} from "./handoverApi";
import { HandoverMarkup } from "./HandoverMarkup";
import {
  EMPTY_HANDOVER_FILTERS,
  filterHandoversBySearch,
  handoverErrorMessage,
  handoverStats,
} from "./handoverUtils";
import type { HandoverFilters, HandoverMessage, HandoverPayload, HandoverRecord, Machine } from "./HandoverTypes";

const HANDOVER_ISLAND = {
  mountedFlag: "maintenanceHandoverReactMounted",
  mountEvent: "maintenance-handover-react-mounted",
} as const;

const HANDOVER_ROOT_SELECTOR = "#maintenance-handover-root";
const HANDOVER_SHELL_SELECTOR = "[data-handover-react-shell]";

/**
 * Convert one handover form submission into an API payload.
 */
function payloadFromForm(form: HTMLFormElement): HandoverPayload {
  const payload: Record<string, string | boolean> = Object.fromEntries(
    new FormData(form).entries()
  ) as Record<string, string>;
  const confirmed = form.elements.namedItem("confirmed");
  payload.confirmed = confirmed instanceof HTMLInputElement ? confirmed.checked : false;
  Object.keys(payload).forEach((key) => {
    if (payload[key] === "") {
      delete payload[key];
    }
  });
  return payload;
}

/**
 * Return whether a handover payload has the required create fields.
 */
function handoverPayloadIsValid(payload: HandoverPayload): boolean {
  return Boolean(payload.department && payload.shift_date && payload.shift_type);
}

/**
 * Render the handover page with React-owned behavior and legacy fallback hooks.
 */
export function HandoverApp(): ReactNode {
  const writable = canWriteDashboard("shiftplans");
  const [dialogMessage, setDialogMessage] = useState<HandoverMessage>({ text: "" });
  const [editHandover, setEditHandover] = useState<HandoverRecord | null>(null);
  const [filters, setFilters] = useState<HandoverFilters>(EMPTY_HANDOVER_FILTERS);
  const [formMessage, setFormMessage] = useState<HandoverMessage>({ text: "" });
  const [handovers, setHandovers] = useState<HandoverRecord[]>([]);
  const [listMessage, setListMessage] = useState<HandoverMessage>({ text: "Einträge werden geladen." });
  const [machines, setMachines] = useState<Machine[]>([]);
  const [savingDialog, setSavingDialog] = useState(false);
  const [showCreateDrawer, setShowCreateDrawer] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const visibleHandovers = useMemo(
    () => filterHandoversBySearch(handovers, filters.search),
    [filters.search, handovers]
  );
  const stats = useMemo(() => handoverStats(handovers), [handovers]);

  /**
   * Refresh machines for assignment and filtering.
   */
  async function refreshMachines(): Promise<void> {
    if (!hasStoredToken()) return;
    setMachines(await loadHandoverMachines());
  }

  /**
   * Refresh handover records with the current or provided filters.
   */
  async function refreshHandovers(nextFilters = filters): Promise<void> {
    if (!hasStoredToken()) {
      setListMessage({ text: "Bitte anmelden, um Schichtübergaben zu sehen.", isError: true });
      return;
    }
    const loadedHandovers = await loadHandovers(nextFilters);
    setHandovers(loadedHandovers);
    setListMessage({ text: "" });
  }

  /**
   * Load initial machines and handovers.
   */
  async function loadInitialData(): Promise<void> {
    await Promise.all([refreshMachines(), refreshHandovers(EMPTY_HANDOVER_FILTERS)]);
  }

  /**
   * Submit the create form.
   */
  async function submitForm(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = payloadFromForm(form);
    if (!handoverPayloadIsValid(payload)) {
      setFormMessage({ text: "Bitte Bereich, Datum und aktuelle Schicht ausfüllen.", isError: true });
      return;
    }
    setSubmitting(true);
    setFormMessage({ text: "Übergabe wird gespeichert..." });
    try {
      await createHandover(payload);
      form.reset();
      setFormMessage({ text: "Übergabe gespeichert." });
      await refreshHandovers(filters);
      setShowCreateDrawer(false);
    } catch (error) {
      setFormMessage({ text: `Fehler: ${handoverErrorMessage(error, "Übergabe konnte nicht gespeichert werden.")}`, isError: true });
    } finally {
      setSubmitting(false);
    }
  }

  /**
   * Apply server-side filters.
   */
  function applyFilters(): void {
    refreshHandovers(filters).catch((error: unknown) => {
      setListMessage({ text: handoverErrorMessage(error), isError: true });
    });
  }

  /**
   * Reset filters and reload all visible handovers.
   */
  function resetFilters(): void {
    setFilters(EMPTY_HANDOVER_FILTERS);
    refreshHandovers(EMPTY_HANDOVER_FILTERS).catch((error: unknown) => {
      setListMessage({ text: handoverErrorMessage(error), isError: true });
    });
  }

  /**
   * Mark one handover as completed.
   */
  async function completeSelectedHandover(handover: HandoverRecord): Promise<void> {
    setListMessage({ text: "Übergabe wird bestätigt..." });
    try {
      await completeHandover(handover.id);
      await refreshHandovers(filters);
      setListMessage({ text: "Übergabe bestätigt." });
    } catch (error) {
      setListMessage({ text: handoverErrorMessage(error, "Übergabe konnte nicht bestätigt werden."), isError: true });
    }
  }

  /**
   * Open one handover for editing.
   */
  function openEditDialog(handover: HandoverRecord): void {
    setDialogMessage({ text: "" });
    setEditHandover(handover);
  }

  /**
   * Move focus to the handover list search field.
   */
  function focusList(): void {
    document.getElementById("handover-list")?.scrollIntoView({ behavior: "smooth", block: "start" });
    document.getElementById("filter-search")?.focus();
  }

  /**
   * Save the edit dialog payload.
   */
  async function saveDialog(id: number, payload: HandoverPayload): Promise<void> {
    setSavingDialog(true);
    setDialogMessage({ text: "Wird gespeichert..." });
    try {
      await updateHandover(id, payload);
      setEditHandover(null);
      setDialogMessage({ text: "" });
      await refreshHandovers(filters);
    } catch (error) {
      setDialogMessage({ text: handoverErrorMessage(error, "Übergabe konnte nicht aktualisiert werden."), isError: true });
    } finally {
      setSavingDialog(false);
    }
  }

  useEffect(() => {
    /**
     * Announce React ownership only after the rendered shell is visible in the root.
     */
    function markMountedWhenShellExists(): void {
      const rootElement = document.querySelector(HANDOVER_ROOT_SELECTOR);
      if (rootElement?.querySelector(HANDOVER_SHELL_SELECTOR)) {
        markIslandMounted(HANDOVER_ISLAND);
      }
    }

    const frameId = window.requestAnimationFrame(markMountedWhenShellExists);
    return () => window.cancelAnimationFrame(frameId);
  }, []);

  useEffect(() => {
    loadInitialData().catch((error: unknown) => {
      setListMessage({ text: handoverErrorMessage(error), isError: true });
    });
    if (window.location.hash === "#handover-workflow") {
      setShowCreateDrawer(true);
    }
  }, []);

  useEffect(
    () =>
      subscribeToSessionChange(() => {
        loadInitialData().catch((error: unknown) => {
          setListMessage({ text: handoverErrorMessage(error), isError: true });
        });
      }),
    []
  );

  return (
    <div data-handover-react-shell>
      <HandoverMarkup
        dialogMessage={dialogMessage}
        editHandover={editHandover}
        filters={filters}
        formMessage={formMessage}
        handovers={visibleHandovers}
        loadedCount={handovers.length}
        listMessage={listMessage}
        machines={machines}
        onCloseDialog={() => setEditHandover(null)}
        onComplete={completeSelectedHandover}
        onCreateClose={() => setShowCreateDrawer(false)}
        onCreateOpen={() => setShowCreateDrawer(true)}
        onEdit={openEditDialog}
        onFilter={applyFilters}
        onFilterChange={setFilters}
        onFocusList={focusList}
        onResetFilters={resetFilters}
        onSaveDialog={saveDialog}
        onSubmit={submitForm}
        savingDialog={savingDialog}
        showCreateDrawer={showCreateDrawer}
        stats={stats}
        submitting={submitting}
        writable={writable}
      />
    </div>
  );
}
