import { useEffect, useMemo, useState, type ReactNode } from "react";

import { confirmAction } from "../app/runtimeBridge";
import { canWriteDashboard } from "../auth/permissions";
import { subscribeToSessionChange } from "../auth/sessionChange";
import { ActionDrawer } from "../components/ui/ActionDrawer";
import { createActionDefinition } from "../components/ui/createActionSchema";
import { PageHeader } from "../components/ui/PageHeader";
import { triggerBrowserDownload } from "../utils/download";
import {
  deleteShiftPlan,
  deleteShiftplanEntry,
  generateShiftPlan,
  loadShiftModels,
  loadShiftPlans,
  loadShiftplanChangelog,
  loadShiftplanConflicts,
  loadShiftplanMachines,
  moveEntryToEntry,
  moveEntryToSlot,
  previewShiftPlan,
  publishShiftPlan,
  shiftplanExportUrl,
  updateShiftplanEntry,
} from "./shiftplanApi";
import { ShiftplansEditDialog } from "./components/ShiftplansEditDialog";
import { ShiftplansGenerationForm } from "./components/ShiftplansGenerationForm";
import { ShiftplansPlanView } from "./components/ShiftplansPlanView";
import type {
  Machine,
  ShiftModel,
  ShiftPlan,
  ShiftplanChangeLog,
  ShiftplanEditDraft,
  ShiftplanEntry,
  ShiftplansMessage,
  ShiftplanDraft,
  ShiftplanWarning,
} from "./shiftplanTypes";
import {
  EMPTY_SHIFTPLAN_DRAFT,
  buildGenerationPayload,
  shiftplansErrorMessage,
} from "./shiftplanUtils";
import {
  currentUserIsAdmin,
  plansWithFallback,
  selectedPlanIndexFor,
} from "./shiftplanModel";

/**
 * Shift planning: generate, review, publish and adjust plans per department.
 */
export function ShiftplansApp(): ReactNode {
  const writable = canWriteDashboard("shiftplans");
  const [busyAction, setBusyAction] = useState<"generate" | "preview" | null>(null);
  const [changelog, setChangelog] = useState<ShiftplanChangeLog[]>([]);
  const [deletingEntry, setDeletingEntry] = useState(false);
  const [dialogEntry, setDialogEntry] = useState<ShiftplanEntry | null>(null);
  const [dialogMessage, setDialogMessage] = useState<ShiftplansMessage>({ text: "" });
  const [draft, setDraft] = useState<ShiftplanDraft>(EMPTY_SHIFTPLAN_DRAFT);
  const [formMessage, setFormMessage] = useState<ShiftplansMessage>({ text: "Schichtplanung wird geladen..." });
  const [isAdmin, setIsAdmin] = useState(currentUserIsAdmin());
  const [machines, setMachines] = useState<Machine[]>([]);
  const [models, setModels] = useState<ShiftModel[]>([]);
  const [plans, setPlans] = useState<ShiftPlan[]>([]);
  const [savingEntry, setSavingEntry] = useState(false);
  const [selectedMachineIds, setSelectedMachineIds] = useState<ReadonlySet<number>>(new Set());
  const [selectedPlanIndex, setSelectedPlanIndex] = useState(0);
  const [showGenerateDrawer, setShowGenerateDrawer] = useState(false);
  const [warnings, setWarnings] = useState<ShiftplanWarning[]>([]);

  const currentPlan = plans[selectedPlanIndex] || null;
  const selectedModel = useMemo(
    () => models.find((model) => model.key === draft.shiftModelKey) || null,
    [draft.shiftModelKey, models]
  );


  /**
   * Load initial data for models, machines, and plans.
   */
  async function refreshInitialData(selectPlanId?: number, fallbackPlan: ShiftPlan | null = null): Promise<void> {
    setIsAdmin(currentUserIsAdmin());
    const [loadedModels, loadedMachines, loadedPlans] = await Promise.all([
      loadShiftModels(),
      loadShiftplanMachines(),
      loadShiftPlans(),
    ]);
    const nextPlans = plansWithFallback(loadedPlans, fallbackPlan);
    setModels(loadedModels);
    setMachines(loadedMachines);
    setSelectedMachineIds((current) => (
      current.size ? current : new Set(loadedMachines.map((machine) => machine.id))
    ));
    setPlans(nextPlans);
    setSelectedPlanIndex(selectedPlanIndexFor(nextPlans, selectPlanId));
    setFormMessage({ text: "" });
  }

  /**
   * Load warning and changelog details for the current plan.
   */
  async function refreshPlanDetails(plan: ShiftPlan | null): Promise<void> {
    if (!plan?.id) {
      setWarnings(plan?.warnings ? [...plan.warnings] : []);
      setChangelog([]);
      return;
    }
    const conflictPayload = await loadShiftplanConflicts(plan.id).catch(() => ({ conflicts: plan.warnings || [] }));
    setWarnings([...(conflictPayload.conflicts || plan.warnings || [])]);
    if (currentUserIsAdmin()) {
      setChangelog(await loadShiftplanChangelog(plan.id).catch(() => []));
    } else {
      setChangelog([]);
    }
  }

  useEffect(() => {
    refreshInitialData().catch((error: unknown) => {
      setFormMessage({ text: shiftplansErrorMessage(error, "Schichtplanung konnte nicht geladen werden."), isError: true });
    });
    if (window.location.hash === "#shiftplan-generate") {
      setShowGenerateDrawer(true);
    }
  }, []);

  useEffect(() => {
    refreshPlanDetails(currentPlan).catch(() => undefined);
  }, [currentPlan?.id, currentPlan?.status, selectedPlanIndex]);

  useEffect(() => subscribeToSessionChange(() => {
    refreshInitialData().catch((error: unknown) => {
      setFormMessage({ text: shiftplansErrorMessage(error, "Schichtplanung konnte nicht geladen werden."), isError: true });
    });
  }), []);

  /**
   * Toggle one selected machine.
   */
  function toggleMachine(machineId: number, checked: boolean): void {
    setSelectedMachineIds((current) => {
      const next = new Set(current);
      if (checked) next.add(machineId);
      else next.delete(machineId);
      return next;
    });
  }

  /**
   * Generate a preview or persisted plan.
   */
  async function submitPlan(mode: "generate" | "preview"): Promise<void> {
    let payload;
    try {
      payload = buildGenerationPayload(draft, selectedModel, Array.from(selectedMachineIds));
    } catch (error) {
      setFormMessage({ text: shiftplansErrorMessage(error), isError: true });
      return;
    }

    setBusyAction(mode);
    setFormMessage({ text: mode === "preview" ? "Vorschau wird erstellt..." : "Plan wird generiert..." });
    try {
      const plan = mode === "preview" ? await previewShiftPlan(payload) : await generateShiftPlan(payload);
      setFormMessage({ text: mode === "preview" ? "Vorschau erstellt. Noch nicht gespeichert." : "Plan erfolgreich generiert." });
      setWarnings([...(plan.warnings || [])]);
      await refreshInitialData(plan.id, plan);
      if (mode === "generate") {
        setShowGenerateDrawer(false);
      }
    } catch (error) {
      setFormMessage({ text: `Fehler: ${shiftplansErrorMessage(error)}`, isError: true });
    } finally {
      setBusyAction(null);
    }
  }

  /**
   * Persist the current dialog entry.
   */
  async function saveDialog(entry: ShiftplanEntry, editDraft: ShiftplanEditDraft): Promise<void> {
    setSavingEntry(true);
    setDialogMessage({ text: "Wird gespeichert..." });
    try {
      const updatedPlan = await updateShiftplanEntry(entry.id, editDraft);
      await refreshInitialData(updatedPlan.id, updatedPlan);
      setDialogEntry(null);
      setDialogMessage({ text: "" });
    } catch (error) {
      setDialogMessage({ text: shiftplansErrorMessage(error), isError: true });
    } finally {
      setSavingEntry(false);
    }
  }

  /**
   * Delete one shiftplan entry after confirmation.
   */
  async function deleteEntry(entry: ShiftplanEntry): Promise<void> {
    if (!(await confirmAction({ title: "Schichteintrag löschen", message: "Eintrag wirklich löschen?", confirmText: "Löschen" }))) return;
    setDeletingEntry(true);
    try {
      await deleteShiftplanEntry(entry.id);
      await refreshInitialData(currentPlan?.id);
      setDialogEntry(null);
    } catch (error) {
      setDialogMessage({ text: shiftplansErrorMessage(error), isError: true });
    } finally {
      setDeletingEntry(false);
    }
  }

  /**
   * Move one entry to an empty slot and reload the plan.
   */
  async function moveToSlot(entryId: number, targetDate: string, targetShift: string): Promise<void> {
    try {
      const updatedPlan = await moveEntryToSlot(entryId, targetDate, targetShift);
      await refreshInitialData(updatedPlan.id, updatedPlan);
    } catch (error) {
      setFormMessage({ text: `Fehler beim Verschieben: ${shiftplansErrorMessage(error)}`, isError: true });
    }
  }

  /**
   * Move one entry onto another entry and reload the plan.
   */
  async function moveToEntry(entryId: number, targetEntryId: number): Promise<void> {
    try {
      const updatedPlan = await moveEntryToEntry(entryId, targetEntryId);
      await refreshInitialData(updatedPlan.id, updatedPlan);
    } catch (error) {
      setFormMessage({ text: `Fehler beim Tauschen: ${shiftplansErrorMessage(error)}`, isError: true });
    }
  }

  /**
   * Toggle the publication state for the current plan.
   */
  async function togglePublish(): Promise<void> {
    if (!currentPlan?.id) return;
    const willPublish = currentPlan.status !== "published";
    if (willPublish) {
      const conflicts = await loadShiftplanConflicts(currentPlan.id).catch(() => null);
      const criticalCount = conflicts?.summary?.critical || 0;
      if (criticalCount > 0 && !(await confirmAction({
        title: "Kritische Konflikte",
        message: `Der Plan hat ${criticalCount} kritische Konflikte. Trotzdem veröffentlichen?`,
        confirmText: "Veröffentlichen",
      }))) {
        setWarnings([...(conflicts?.conflicts || [])]);
        return;
      }
    }
    const confirmed = await confirmAction(willPublish
      ? { title: "Plan veröffentlichen", message: `„${currentPlan.title}“ veröffentlichen? Mitarbeiter können ihn dann sehen.`, confirmText: "Veröffentlichen" }
      : { title: "Zurück auf Entwurf", message: "Der Plan wird für Mitarbeiter ausgeblendet.", confirmText: "Auf Entwurf setzen" });
    if (!confirmed) return;
    const updatedPlan = await publishShiftPlan(currentPlan.id);
    await refreshInitialData(updatedPlan.id, updatedPlan);
  }

  /**
   * Delete the current plan after confirmation.
   */
  async function removeCurrentPlan(): Promise<void> {
    if (!currentPlan?.id) return;
    const confirmed = await confirmAction({
      title: "Plan löschen",
      message: `„${currentPlan.title}“ wirklich löschen?`,
      confirmText: "Löschen",
    });
    if (!confirmed) return;
    await deleteShiftPlan(currentPlan.id);
    await refreshInitialData();
  }

  /**
   * Download the current plan as an Excel file.
   */
  function downloadCurrentPlan(): void {
    if (!currentPlan?.id) return;
    triggerBrowserDownload(shiftplanExportUrl(currentPlan.id), `${currentPlan.title || "schichtplan"}.xlsx`);
  }

  return (
    <>
      <div className="no-print">
        <PageHeader
          title="Schichtplan"
          description="Abteilung auswählen, Zeitraum festlegen und Plan generieren."
          actions={[
            { hidden: !writable, onClick: () => setShowGenerateDrawer(true), schema: createActionDefinition("shiftplanGenerate"), variant: "primary" },
            { label: "Drucken", onClick: () => window.print() }
          ]}
        />
      </div>
      <section className="dashboard-grid">
        <ShiftplansPlanView
          changelog={changelog}
          currentPlan={currentPlan}
          isAdmin={isAdmin}
          onDeleteEntry={deleteEntry}
          onDeletePlan={removeCurrentPlan}
          onDownload={downloadCurrentPlan}
          onEditEntry={(entry) => {
            setDialogMessage({ text: "" });
            setDialogEntry(entry);
          }}
          onMoveEntryToEntry={moveToEntry}
          onMoveEntryToSlot={moveToSlot}
          onPlanSelect={setSelectedPlanIndex}
          onPrint={() => window.print()}
          onPublish={() => {
            togglePublish().catch((error: unknown) => {
              setFormMessage({ text: shiftplansErrorMessage(error), isError: true });
            });
          }}
          plans={plans}
          selectedPlanIndex={selectedPlanIndex}
          warnings={warnings}
          writable={writable}
        />
      </section>
      <ShiftplansEditDialog
        deleting={deletingEntry}
        entry={dialogEntry}
        isAdmin={isAdmin}
        message={dialogMessage}
        onClose={() => setDialogEntry(null)}
        onDelete={deleteEntry}
        onSave={saveDialog}
        saving={savingEntry}
      />
      <ActionDrawer
        definition={createActionDefinition("shiftplanGenerate")}
        isOpen={showGenerateDrawer}
        onClose={() => setShowGenerateDrawer(false)}
      >
        <ShiftplansGenerationForm
          busyAction={busyAction}
          draft={draft}
          machines={machines}
          message={formMessage}
          models={models}
          onDraftChange={setDraft}
          onGenerate={() => submitPlan("generate")}
          onMachineToggle={toggleMachine}
          onPreview={() => submitPlan("preview")}
          selectedMachineIds={selectedMachineIds}
          writable={writable}
        />
      </ActionDrawer>
    </>
  );
}
