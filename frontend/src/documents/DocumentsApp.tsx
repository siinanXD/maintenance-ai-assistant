import {
  useEffect,
  useState,
  type ReactNode
} from "react";

import { markIslandMounted } from "../app/islandMount";
import { canWriteDashboard } from "../auth/permissions";
import { ActionDrawer } from "../components/ui/ActionDrawer";
import { createActionDefinition } from "../components/ui/createActionSchema";
import { loadGeneratedDocuments, loadMachineManuals, loadMachines } from "./documentApi";
import { DocumentFilterPanel } from "./components/DocumentFilterPanel";
import { DocumentHeader } from "./components/DocumentHeader";
import { DocumentInsightPanels } from "./components/DocumentInsightPanels";
import { GeneratedDocumentList, ManualList } from "./components/DocumentLists";
import { DocumentStats } from "./components/DocumentStats";
import {
  ManualUploadPanel,
  UploadCheckPanel
} from "./components/DocumentPanels";
import type {
  DocumentFilters,
  DocumentReview,
  DocumentSummary,
  GeneratedDocument,
  Machine,
  MachineManual,
  MessageState
} from "./documentTypes";
import { documentErrorMessage, emptyDocumentFilters } from "./documentUtils";

const DOCUMENTS_ISLAND = {
  mountedFlag: "maintenanceDocumentsReactMounted",
  mountEvent: "maintenance-documents-react-mounted"
};

/**
 * Render the React documents workflow island.
 */
export function DocumentsApp(): ReactNode {
  const writable = canWriteDashboard("documents");
  const [activeDrawer, setActiveDrawer] = useState<"filter" | "manual" | "upload-check" | null>(null);
  const [documents, setDocuments] = useState<GeneratedDocument[]>([]);
  const [filters, setFilters] = useState<DocumentFilters>(emptyDocumentFilters());
  const [manuals, setManuals] = useState<MachineManual[]>([]);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [message, setMessage] = useState<MessageState>({ text: "", error: false });
  const [review, setReview] = useState<DocumentReview | null>(null);
  const [summary, setSummary] = useState<DocumentSummary | null>(null);

  /**
   * Load generated documents with current filters.
   */
  async function refreshDocuments(nextFilters = filters): Promise<void> {
    setDocuments(await loadGeneratedDocuments(nextFilters));
  }

  /**
   * Load manuals and machine choices.
   */
  async function refreshManuals(): Promise<void> {
    const [loadedManuals, loadedMachines] = await Promise.all([
      loadMachineManuals(),
      loadMachines()
    ]);
    setManuals(loadedManuals);
    setMachines(loadedMachines);
  }

  /**
   * Submit filter changes and update the visible document list.
   */
  async function submitFilters(): Promise<void> {
    setMessage({ text: "Dokumente werden geladen...", error: false });
    try {
      await refreshDocuments(filters);
      setMessage({ text: "Dokumentliste aktualisiert.", error: false });
    } catch (error) {
      setMessage({ text: documentErrorMessage(error), error: true });
    }
  }

  useEffect(() => {
    markIslandMounted(DOCUMENTS_ISLAND);
  }, []);

  useEffect(() => {
    Promise.all([refreshDocuments(), refreshManuals()])
      .then(() => {
        setMessage({ text: "Dokumentaktionen bereit.", error: false });
      })
      .catch((error: unknown) => {
        setMessage({ text: documentErrorMessage(error), error: true });
      });
  }, []);

  return (
    <>
      <DocumentHeader
        onFilterOpen={() => setActiveDrawer("filter")}
        onManualUploadOpen={() => setActiveDrawer("manual")}
        onUploadCheckOpen={() => setActiveDrawer("upload-check")}
        writable={writable}
      />
      <DocumentStats documents={documents} manuals={manuals} />
      <DocumentInsightPanels review={review} summary={summary} />
      <section className="dashboard-grid documents-work-grid">
        <GeneratedDocumentList
          documents={documents}
          onMessage={setMessage}
          onRefresh={refreshDocuments}
          onReview={setReview}
          onSummary={setSummary}
          writable={writable}
        />
        <ManualList
          manuals={manuals}
          onRefresh={refreshManuals}
          onSummary={setSummary}
          writable={writable}
        />
      </section>
      <ActionDrawer
        definition={createActionDefinition("documentFilter")}
        isOpen={activeDrawer === "filter"}
        onClose={() => setActiveDrawer(null)}
      >
        <DocumentFilterPanel
          drawerMode
          filters={filters}
          message={message}
          onFiltersChange={setFilters}
          onSubmit={async () => {
            await submitFilters();
            setActiveDrawer(null);
          }}
        />
      </ActionDrawer>
      <ActionDrawer
        definition={createActionDefinition("documentUploadCheck")}
        isOpen={activeDrawer === "upload-check"}
        onClose={() => setActiveDrawer(null)}
      >
        <UploadCheckPanel onReview={(nextReview) => {
          setReview(nextReview);
          setActiveDrawer(null);
        }} />
      </ActionDrawer>
      <ActionDrawer
        definition={createActionDefinition("documentManualUpload")}
        isOpen={activeDrawer === "manual"}
        onClose={() => setActiveDrawer(null)}
      >
        <ManualUploadPanel
          machines={machines}
          onUploaded={async () => {
            await refreshManuals();
            setActiveDrawer(null);
          }}
        />
      </ActionDrawer>
    </>
  );
}
