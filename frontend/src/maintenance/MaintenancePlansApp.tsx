import { useEffect, useMemo, useState, type ReactNode } from "react";

import { markIslandMounted } from "../app/islandMount";
import { canWriteDashboard } from "../auth/permissions";
import { ActionDrawer } from "../components/ui/ActionDrawer";
import { PlanForm } from "./components/PlanForm";
import { PlanRow } from "./components/PlanRow";
import { RecordForm } from "./components/RecordForm";
import { DUE_STATE_LABELS, draftFromPlan, emptyPlanDraft } from "./maintenanceLabels";
import { loadMachineOptions, loadPlans } from "./maintenanceApi";
import type { DueState, MachineOption, MaintenancePlan, PlanDraft, PlanKind } from "./maintenanceTypes";

const MAINTENANCE_ISLAND = {
  mountedFlag: "maintenanceMaintenanceReactMounted",
  mountEvent: "maintenance-maintenance-react-mounted"
};

const GROUP_ORDER: readonly DueState[] = ["overdue", "due_soon", "ok", "inactive"];

type Drawer =
  | { readonly type: "plan"; readonly planId: number | null }
  | { readonly type: "record"; readonly plan: MaintenancePlan }
  | null;

/**
 * Inspections and maintenance: what is due, proof of execution, next date.
 */
export function MaintenancePlansApp(): ReactNode {
  const writable = canWriteDashboard("machines");
  const [plans, setPlans] = useState<MaintenancePlan[] | null>(null);
  const [machines, setMachines] = useState<MachineOption[]>([]);
  const [kind, setKind] = useState<"" | PlanKind>("");
  const [drawer, setDrawer] = useState<Drawer>(null);
  const [draft, setDraft] = useState<PlanDraft>(emptyPlanDraft());
  const [message, setMessage] = useState({ text: "", error: false });

  /**
   * Reload plans and machine options.
   */
  async function refresh(): Promise<void> {
    const [loadedPlans, loadedMachines] = await Promise.all([loadPlans(), loadMachineOptions()]);
    setPlans(loadedPlans);
    setMachines([...loadedMachines].sort((first, second) => first.name.localeCompare(second.name, "de-DE")));
  }

  useEffect(() => {
    markIslandMounted(MAINTENANCE_ISLAND);
    refresh().catch((error: unknown) => {
      setPlans([]);
      setMessage({ text: error instanceof Error ? error.message : "Pläne konnten nicht geladen werden.", error: true });
    });
  }, []);

  const visiblePlans = useMemo(() => (plans || []).filter((plan) => !kind || plan.kind === kind), [plans, kind]);
  const counts = useMemo(() => {
    const result: Record<DueState, number> = { overdue: 0, due_soon: 0, ok: 0, inactive: 0 };
    visiblePlans.forEach((plan) => { result[plan.due_state] += 1; });
    return result;
  }, [visiblePlans]);

  /**
   * Open the plan form for a new or existing plan.
   */
  function openPlan(plan: MaintenancePlan | null): void {
    setDraft(plan ? draftFromPlan(plan) : emptyPlanDraft());
    setDrawer({ type: "plan", planId: plan?.id ?? null });
  }

  /**
   * Close the drawer, reload and show a confirmation.
   */
  async function afterSave(text: string): Promise<void> {
    setDrawer(null);
    setMessage({ text, error: false });
    await refresh();
  }

  return (
    <>
      <header className="page-intro">
        <div>
          <h1 className="page-title">Prüfungen &amp; Wartung</h1>
          <p className="page-description">Prüfpflichten und Wartungspläne mit Nachweis. Überfälliges steht oben.</p>
        </div>
        {writable ? <button className="btn btn-primary" data-plan-create type="button" onClick={() => openPlan(null)}>Plan anlegen</button> : null}
      </header>

      <section className="plan-summary" aria-label="Fälligkeiten">
        {GROUP_ORDER.slice(0, 3).map((state) => (
          <a className={`plan-summary-item is-${state}`} href={`#plans-${state}`} key={state}>
            <strong>{counts[state]}</strong>
            <span>{DUE_STATE_LABELS[state]}</span>
          </a>
        ))}
        <div className="plan-filter" role="group" aria-label="Art filtern">
          {([["", "Alle"], ["inspection", "Prüfpflichten"], ["maintenance", "Wartung"]] as const).map(([value, label]) => (
            <button aria-pressed={kind === value} className={`filter-chip${kind === value ? " is-active" : ""}`} key={value} type="button" onClick={() => setKind(value)}>{label}</button>
          ))}
        </div>
      </section>

      {message.text ? <p className={`workflow-status${message.error ? " is-error" : ""}`} role="status">{message.text}</p> : null}

      {plans === null ? <p className="panel-meta">Pläne werden geladen…</p> : null}
      {plans && !visiblePlans.length ? (
        <div className="guided-empty-state">
          <strong>Noch keine Pläne</strong>
          <p>Lege wiederkehrende Prüfungen wie DGUV V3 oder Wartungen mit Intervall an. Jede Durchführung wird mit Ergebnis dokumentiert.</p>
        </div>
      ) : null}

      {GROUP_ORDER.map((state) => {
        const group = visiblePlans.filter((plan) => plan.due_state === state);
        if (!group.length) return null;
        return (
          <section className={`plan-group is-${state}`} id={`plans-${state}`} key={state}>
            <h2>{DUE_STATE_LABELS[state]} <span>{group.length}</span></h2>
            <ul className="plan-list">
              {group.map((plan) => (
                <PlanRow key={plan.id} plan={plan} writable={writable} onEdit={openPlan} onRecord={(item) => setDrawer({ type: "record", plan: item })} />
              ))}
            </ul>
          </section>
        );
      })}

      <ActionDrawer
        description="Intervall, Maschine und bei Prüfpflichten die Rechtsgrundlage festlegen."
        isOpen={drawer?.type === "plan"}
        title={drawer?.type === "plan" && drawer.planId ? "Plan bearbeiten" : "Plan anlegen"}
        onClose={() => setDrawer(null)}
      >
        {drawer?.type === "plan" ? (
          <PlanForm draft={draft} machines={machines} planId={drawer.planId} onDraftChange={setDraft} onSaved={(plan) => afterSave(`„${plan.title}“ gespeichert.`)} />
        ) : null}
      </ActionDrawer>
      <ActionDrawer
        description="Datum, Prüfer und Ergebnis dokumentieren. Die nächste Fälligkeit wird berechnet."
        isOpen={drawer?.type === "record"}
        title="Durchführung dokumentieren"
        onClose={() => setDrawer(null)}
      >
        {drawer?.type === "record" ? <RecordForm plan={drawer.plan} onSaved={afterSave} /> : null}
      </ActionDrawer>
    </>
  );
}
