import type { ReactNode } from "react";

import { PageActionBar } from "../../components/ui/PageActionBar";
import { createActionDefinition } from "../../components/ui/createActionSchema";

type MachinesHeaderProps = {
  readonly issueCount: number;
  readonly onAssistantFocus: () => void;
  readonly onCreateMachine: () => void;
  readonly writable: boolean;
};

/**
 * Render machine overview hero and quick actions.
 */
export function MachinesHeader({
  issueCount,
  onAssistantFocus,
  onCreateMachine,
  writable
}: MachinesHeaderProps): ReactNode {
  return (
    <section className="page-hero is-compact">
      <div>
        <h1 className="page-title">Maschinen</h1>
        <p className="page-description">
          Status, offene Arbeit, Kennzahlen und QR-Etikett je Anlage.
        </p>
      </div>
      <PageActionBar
        label="Maschinen Aktionen"
        actions={[
          { hidden: !writable, onClick: onCreateMachine, schema: createActionDefinition("machineCreate"), variant: "primary" },
          { label: "Maschine prüfen", onClick: onAssistantFocus, variant: "outline" },
          { hidden: issueCount === 0, href: "/errors", label: `${issueCount} Störungen`, variant: "ghost" }
        ]}
      />
    </section>
  );
}
