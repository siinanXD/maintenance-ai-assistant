import type { ReactNode } from "react";

import { PageActionBar } from "../../components/ui/PageActionBar";
import { createActionDefinition } from "../../components/ui/createActionSchema";

type DocumentHeaderProps = {
  readonly onFilterOpen: () => void;
  readonly onManualUploadOpen: () => void;
  readonly onUploadCheckOpen: () => void;
  readonly writable: boolean;
};

/**
 * Render document page header and actions.
 */
export function DocumentHeader({
  onFilterOpen,
  onManualUploadOpen,
  onUploadCheckOpen,
  writable
}: DocumentHeaderProps): ReactNode {
  return (
    <section className="page-hero is-compact">
      <div>
        <h1 className="page-title">Dokumentenübersicht</h1>
        <p className="page-description">
          Berichte und Handbücher als Wissensbasis prüfen, freigeben und herunterladen.
        </p>
      </div>
      <PageActionBar
        label="Dokumente Aktionen"
        actions={[
          { hidden: !writable, onClick: onManualUploadOpen, schema: createActionDefinition("documentManualUpload"), variant: "primary" },
          { hidden: !writable, onClick: onUploadCheckOpen, schema: createActionDefinition("documentUploadCheck"), variant: "outline" },
          { onClick: onFilterOpen, schema: createActionDefinition("documentFilter"), variant: "ghost" }
        ]}
      />
    </section>
  );
}
