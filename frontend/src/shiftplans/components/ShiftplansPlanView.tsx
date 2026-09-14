import { type ReactNode } from "react";

import { ShiftplansAdminDetails } from "./ShiftplansAdminDetails";
import { ShiftplansCalendar } from "./ShiftplansCalendar";
import { ShiftplansPlanActions, ShiftplansSelector } from "./ShiftplansPlanActions";
import { ShiftplansStats } from "./ShiftplansStats";
import type { ShiftplansPlanViewProps } from "./planViewTypes";

/**
 * Render the shiftplan view card and all runtime-controlled child containers.
 */
export function ShiftplansPlanView(props: ShiftplansPlanViewProps): ReactNode {
  return (
    <article className="card app-card lg:col-span-12" id="sp-view-card">
      <div className="card-body">
        <div className="panel-header no-print">
          <div>
            <h2 className="panel-title" id="sp-view-title">
              Schichtpläne
            </h2>
            <p className="panel-meta" id="sp-view-meta">
              Zuletzt generierte Pläne
            </p>
          </div>
          <ShiftplansPlanActions currentPlan={props.currentPlan} isAdmin={props.isAdmin} onDownload={props.onDownload} onPrint={props.onPrint} onPublish={props.onPublish} />
        </div>
        <ShiftplansSelector onPlanSelect={props.onPlanSelect} plans={props.plans} selectedPlanIndex={props.selectedPlanIndex} />
        <p className="panel-meta" id="sp-empty-msg" hidden={props.plans.length > 0}>
          Noch keine Schichtpläne vorhanden. Plan generieren um zu starten.
        </p>
        <ShiftplansCalendar
          currentPlan={props.currentPlan}
          onDeleteEntry={props.onDeleteEntry}
          onEditEntry={props.onEditEntry}
          onMoveEntryToEntry={props.onMoveEntryToEntry}
          onMoveEntryToSlot={props.onMoveEntryToSlot}
          writable={props.writable}
        />
        <ShiftplansStats currentPlan={props.currentPlan} />
        <ShiftplansAdminDetails changelog={props.changelog} currentPlan={props.currentPlan} isAdmin={props.isAdmin} onDeletePlan={props.onDeletePlan} warnings={props.warnings} />
      </div>
    </article>
  );
}
