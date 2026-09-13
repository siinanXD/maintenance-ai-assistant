import {
  useEffect,
  useMemo,
  useState,
  type ReactNode
} from "react";

import { markIslandMounted } from "../app/islandMount";
import { canWriteDashboard } from "../auth/permissions";
import { ActionDrawer } from "../components/ui/ActionDrawer";
import { createActionDefinition } from "../components/ui/createActionSchema";
import { ErrorAnalysisPanel } from "./components/ErrorAnalysisPanel";
import { ErrorCatalog } from "./components/ErrorCatalog";
import { ErrorCreatePanel } from "./components/ErrorCreatePanel";
import { ErrorEditDialog } from "./components/ErrorEditDialog";
import { ErrorHeader } from "./components/ErrorHeader";
import { ErrorStats } from "./components/ErrorStats";
import { SimilarErrorsPanel } from "./components/SimilarErrorsPanel";
import { loadDepartments, loadErrors } from "./errorApi";
import type {
  Department,
  ErrorDraft,
  ErrorEntry,
  ErrorFilters,
  MessageState,
  SimilarErrorResult
} from "./errorTypes";
import {
  createEmptyErrorDraft,
  errorMessage,
  initialErrorSearchQuery
} from "./errorUtils";

const ERRORS_ISLAND = {
  mountedFlag: "maintenanceErrorsReactMounted",
  mountEvent: "maintenance-errors-react-mounted"
};

/**
 * Return the user's first visible department as form default.
 */
function defaultDepartment(departments: readonly Department[]): string {
  return departments[0]?.name || "";
}

/**
 * Render the React errors workflow island.
 */
export function ErrorsApp(): ReactNode {
  const writable = canWriteDashboard("errors");
  const [activeDrawer, setActiveDrawer] = useState<"analysis" | "create" | null>(null);
  const [createDraft, setCreateDraft] = useState<ErrorDraft>(createEmptyErrorDraft());
  const [departments, setDepartments] = useState<Department[]>([]);
  const [editingError, setEditingError] = useState<ErrorEntry | null>(null);
  const [errors, setErrors] = useState<ErrorEntry[]>([]);
  const [filters, setFilters] = useState<ErrorFilters>({
    search: initialErrorSearchQuery(),
    status: "",
    severity: "",
    category: "",
    quick: "all"
  });
  const [message, setMessage] = useState<MessageState>({ text: "", error: false });
  const [similarResult, setSimilarResult] = useState<SimilarErrorResult | null>(null);

  const currentDepartment = useMemo(
    () => createDraft.department || defaultDepartment(departments),
    [createDraft.department, departments]
  );

  /**
   * Refresh departments and visible errors in parallel.
   */
  async function refreshErrorsData(): Promise<void> {
    const [loadedDepartments, loadedErrors] = await Promise.all([
      loadDepartments(),
      loadErrors()
    ]);
    setDepartments(loadedDepartments);
    setErrors(loadedErrors);
    setCreateDraft((draft) => ({
      ...draft,
      department: draft.department || defaultDepartment(loadedDepartments)
    }));
  }

  /**
   * Focus the catalog search input.
   */
  function focusSearch(): void {
    document.querySelector<HTMLInputElement>("[data-error-search]")?.focus();
  }

  /**
   * Apply a draft produced by AI analysis and open the create drawer.
   */
  function applyDraft(draft: ErrorDraft): void {
    setCreateDraft(draft);
    setActiveDrawer("create");
  }

  useEffect(() => {
    markIslandMounted(ERRORS_ISLAND);
  }, []);

  useEffect(() => {
    refreshErrorsData().catch((error: unknown) => {
      setMessage({ text: errorMessage(error), error: true });
    });
    if (window.location.hash === "#incident-create") {
      const machine = new URLSearchParams(window.location.search).get("machine");
      if (machine) setCreateDraft((draft) => ({ ...draft, machine }));
      setActiveDrawer("create");
    }
  }, []);

  return (
    <>
      <ErrorHeader
        onAnalysisOpen={() => setActiveDrawer("analysis")}
        onCreateOpen={() => setActiveDrawer("create")}
        onSearchFocus={focusSearch}
        writable={writable}
      />
      <ErrorStats errors={errors} />
      {message.text ? (
        <section className="card app-card" role="alert">
          <div className="card-body">
            <p className={`panel-meta${message.error ? " is-error" : ""}`}>{message.text}</p>
          </div>
        </section>
      ) : null}
      <SimilarErrorsPanel result={similarResult} />
      <ErrorCatalog
        errors={errors}
        filters={filters}
        onEdit={setEditingError}
        onFiltersChange={setFilters}
        onMessageChange={setMessage}
        onMutated={refreshErrorsData}
        onSimilarResult={setSimilarResult}
        writable={writable}
      />
      <ErrorEditDialog
        departments={departments}
        entry={editingError}
        onClose={() => setEditingError(null)}
        onMessageChange={setMessage}
        onSaved={refreshErrorsData}
      />
      <ActionDrawer
        definition={createActionDefinition("errorCreate")}
        isOpen={activeDrawer === "create"}
        onClose={() => setActiveDrawer(null)}
      >
        <ErrorCreatePanel
          departments={departments}
          drawerMode
          draft={createDraft}
          hidden={!writable}
          message={message}
          onDraftChange={setCreateDraft}
          onMessageChange={setMessage}
          onSaved={async () => {
            await refreshErrorsData();
            setActiveDrawer(null);
          }}
          onSimilarResult={setSimilarResult}
        />
      </ActionDrawer>
      <ActionDrawer
        definition={createActionDefinition("errorSuggestion")}
        isOpen={activeDrawer === "analysis"}
        onClose={() => setActiveDrawer(null)}
      >
        <ErrorAnalysisPanel
          currentDepartment={currentDepartment}
          drawerMode
          hidden={!writable}
          onApplyDraft={applyDraft}
          onSimilarResult={setSimilarResult}
        />
      </ActionDrawer>
    </>
  );
}
