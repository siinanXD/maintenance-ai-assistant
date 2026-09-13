import type { ReactNode } from "react";

import { PageActionBar } from "../../components/ui/PageActionBar";
import { createActionDefinition } from "../../components/ui/createActionSchema";

type ErrorHeaderProps = {
  readonly onAnalysisOpen: () => void;
  readonly onSearchFocus: () => void;
  readonly onCreateOpen: () => void;
  readonly writable: boolean;
};

/**
 * Render the incident hub hero and quick actions.
 */
export function ErrorHeader({
  onAnalysisOpen,
  onCreateOpen,
  onSearchFocus,
  writable
}: ErrorHeaderProps): ReactNode {
  return (
    <section className="page-hero incident-hub-hero is-compact">
      <div>
        <h1 className="page-title">Störungszentrale & Fehlerkatalog</h1>
        <p className="page-description">
          Störungen strukturiert erfassen, bekannte Fehler finden und Lösungen als Wissensbasis pflegen.
        </p>
      </div>
      <PageActionBar
        label="Störungen Aktionen"
        actions={[
          { hidden: !writable, onClick: onCreateOpen, schema: createActionDefinition("errorCreate"), variant: "primary" },
          { label: "Katalog durchsuchen", onClick: onSearchFocus, variant: "outline" },
          { hidden: !writable, onClick: onAnalysisOpen, schema: createActionDefinition("errorSuggestion"), variant: "ghost" }
        ]}
      />
    </section>
  );
}
