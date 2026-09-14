import { type ReactNode } from "react";

import type { ShiftPlan } from "../shiftplanTypes";
import type { ShiftplansPlanViewProps } from "./planViewTypes";

/**
 * Render the plan action buttons.
 */
export function ShiftplansPlanActions({
  currentPlan,
  isAdmin,
  onDownload,
  onPrint,
  onPublish,
}: Pick<ShiftplansPlanViewProps, "currentPlan" | "isAdmin" | "onDownload" | "onPrint" | "onPublish">): ReactNode {
  const published = currentPlan?.status === "published";
  return (
    <div className="toolbar">
      <button
        className={`btn btn-sm no-print ${published ? "btn-outline" : "btn-primary"}`}
        id="sp-publish-btn"
        hidden={!isAdmin || !currentPlan?.id}
       
        aria-label="Plan veröffentlichen"
        type="button"
        onClick={onPublish}
      >
        {published ? "Zurück zu Entwurf" : "Veröffentlichen"}
      </button>
      <button className="btn btn-ghost btn-sm no-print" id="sp-print-btn" hidden={!currentPlan} aria-label="Plan drucken" type="button" onClick={onPrint}>
        Drucken
      </button>
      <button className="btn btn-ghost btn-sm no-print" id="sp-csv-btn" hidden={!currentPlan?.id} aria-label="Als Excel exportieren" type="button" onClick={onDownload}>
        XLSX
      </button>
    </div>
  );
}

/**
 * Render the plan selector row.
 */
export function ShiftplansSelector({ onPlanSelect, plans, selectedPlanIndex }: Pick<ShiftplansPlanViewProps, "onPlanSelect" | "plans" | "selectedPlanIndex">): ReactNode {
  return (
    <div className="toolbar mb-3 no-print" id="sp-selector" hidden={!plans.length}>
      <label htmlFor="sp-plan-select" className="stat-label">
        Plan:
      </label>
      <select
        className="select select-bordered select-sm"
        id="sp-plan-select"
        aria-label="Schichtplan wählen"
        value={selectedPlanIndex}
        onChange={(event) => onPlanSelect(Number.parseInt(event.currentTarget.value, 10))}
      >
        {plans.map((plan, index) => (
          <option key={`${plan.id || "preview"}-${index}`} value={index}>
            {plan.title}
            {plan.department ? ` [${plan.department}]` : ""}
            {plan.status === "published" ? " [Veröffentlicht]" : " [Entwurf]"}
          </option>
        ))}
      </select>
      <span id="sp-status-badge" className={currentStatusBadgeClass(plans[selectedPlanIndex])} hidden={!plans.length}>
        {currentStatusBadgeLabel(plans[selectedPlanIndex])}
      </span>
    </div>
  );
}

/**
 * Return the status badge class for one plan.
 */
function currentStatusBadgeClass(plan: ShiftPlan | undefined): string {
  if (plan?.status === "preview") return "badge badge-info";
  if (plan?.status === "published") return "Veröffentlicht";
  return "badge badge-ghost";
}

/**
 * Return the status badge label for one plan.
 */
function currentStatusBadgeLabel(plan: ShiftPlan | undefined): string {
  if (plan?.status === "preview") return "Vorschau";
  if (plan?.status === "published") return "Veröffentlicht";
  return "Entwurf";
}
