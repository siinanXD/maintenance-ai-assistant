import type { ReactNode } from "react";

import type { Employee, VacationDraft, VacationSummary } from "../vacationTypes";
import { countVacationWorkdays, vacationValidationError } from "../vacationUtils";

type BalancePreviewProps = {
  readonly draft: VacationDraft;
  readonly selectedBalance: VacationSummary | null;
  readonly selectedEmployee: Employee | null;
};

/**
 * Render the vacation balance preview.
 */
export function BalancePreview(props: BalancePreviewProps): ReactNode {
  const days = countVacationWorkdays(props.draft.startDate, props.draft.endDate);
  const error = vacationValidationError(props.draft, props.selectedBalance);
  let text = "Wähle Mitarbeiter und Zeitraum.";

  if (error) {
    text = error;
  } else if (props.selectedBalance && props.selectedEmployee && days !== null) {
    text = `${props.selectedEmployee.name}: ${props.selectedBalance.available || 0} Tage verfügbar, ${days} Tage angefragt.`;
  } else if (props.selectedBalance && props.selectedEmployee) {
    text = `${props.selectedEmployee.name}: ${props.selectedBalance.available || 0} verfügbar, ${props.selectedBalance.pending || 0} reserviert, ${props.selectedBalance.used || 0} genehmigt.`;
  }

  return <div className={`vacation-balance-preview is-full${error ? " is-error" : ""}`}>{text}</div>;
}
