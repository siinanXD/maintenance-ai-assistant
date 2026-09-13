import { useEffect, useMemo, useState, type ReactNode } from "react";

import { ActionDrawer } from "../components/ui/ActionDrawer";
import { createActionDefinition } from "../components/ui/createActionSchema";
import { PageHeader } from "../components/ui/PageHeader";
import { StatStrip } from "../components/ui/StatStrip";
import {
  loadCurrentUser,
  loadVacationEmployees,
  loadVacationRequests,
  loadVacationSummary,
  previewVacationImpact
} from "./vacationApi";
import { VacationOpsPanels, VacationPendingPanel } from "./components/VacationPanels";
import { VacationRequestPanel } from "./components/VacationRequestPanel";
import type {
  Employee,
  MaintenanceUser,
  MessageState,
  VacationDraft,
  VacationImpact,
  VacationRequest,
  VacationSummary
} from "./vacationTypes";
import {
  countVacationWorkdays,
  currentVacationYear,
  EMPTY_VACATION_DRAFT,
  storedMaintenanceUser,
  vacationErrorMessage,
  vacationValidationError,
  vacationYearOptions
} from "./vacationUtils";

/**
 * Render the React vacations workflow island.
 */
export function VacationsApp(): ReactNode {
  const [isRequestDrawerOpen, setIsRequestDrawerOpen] = useState(false);
  const [draft, setDraft] = useState<VacationDraft>({ ...EMPTY_VACATION_DRAFT });
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [filterStatus, setFilterStatus] = useState("");
  const [impact, setImpact] = useState<VacationImpact | null>(null);
  const [impactMessage, setImpactMessage] = useState<MessageState>({ text: "Die betriebliche Auswirkung erscheint nach der Auswahl.", type: "" });
  const [message, setMessage] = useState<MessageState>({ text: "", type: "" });
  const [requests, setRequests] = useState<VacationRequest[]>([]);
  const [selectedYear, setSelectedYear] = useState(currentVacationYear());
  const [summaries, setSummaries] = useState<VacationSummary[]>([]);
  const [user, setUser] = useState<MaintenanceUser | null>(storedMaintenanceUser());

  const yearOptions = useMemo(() => vacationYearOptions(), []);
  const selectedEmployee = useMemo(() => employees.find((employee) => String(employee.id) === draft.employeeId) || null, [draft.employeeId, employees]);
  const selectedBalance = useMemo(() => selectedBalanceFor(Number(draft.employeeId || 0)), [draft.employeeId, summaries]);
  const pendingRequests = useMemo(() => requests.filter((request) => request.status === "pending"), [requests]);
  const filteredHistory = useMemo(() => (
    filterStatus ? requests.filter((request) => request.status === filterStatus) : requests
  ), [filterStatus, requests]);
  const validationError = vacationValidationError(draft, selectedBalance);
  const submitDisabled = Boolean(validationError && draft.employeeId && draft.startDate && draft.endDate);

  /**
   * Return the balance for one employee id.
   */
  function selectedBalanceFor(employeeId: number): VacationSummary | null {
    return summaries.find((summary) => summary.employee_id === employeeId) || null;
  }

  /**
   * Refresh vacation summary and requests for the selected year.
   */
  async function refreshVacationData(year = selectedYear): Promise<void> {
    const [loadedSummary, loadedRequests] = await Promise.all([
      loadVacationSummary(year),
      loadVacationRequests(year)
    ]);
    setSummaries(loadedSummary);
    setRequests(loadedRequests);
  }

  /**
   * Load the initial user and employee data.
   *
   * Vacation summary and requests are loaded by the selectedYear effect, which also
   * runs on mount; loading them here as well fetched both lists twice per visit.
   */
  async function loadInitialData(): Promise<void> {
    const [loadedUser, loadedEmployees] = await Promise.all([
      loadCurrentUser().catch(() => storedMaintenanceUser()),
      loadVacationEmployees()
    ]);
    setUser(loadedUser);
    setEmployees(loadedEmployees);
  }

  /**
   * Keep the selected year aligned with the selected start date where possible.
   */
  function updateDraft(nextDraft: VacationDraft): void {
    setDraft(nextDraft);
    const startYear = nextDraft.startDate.slice(0, 4);
    if (startYear && yearOptions.includes(startYear) && startYear !== selectedYear) {
      setSelectedYear(startYear);
    }
  }

  useEffect(() => {
    loadInitialData().catch((error: unknown) => {
      setMessage({ text: vacationErrorMessage(error), type: "error" });
    });
    if (window.location.hash === "#vacation-request") {
      setIsRequestDrawerOpen(true);
    }
  }, []);

  useEffect(() => {
    refreshVacationData(selectedYear).catch((error: unknown) => {
      setMessage({ text: vacationErrorMessage(error), type: "error" });
    });
  }, [selectedYear]);

  useEffect(() => {
    const days = countVacationWorkdays(draft.startDate, draft.endDate);
    if (!draft.employeeId || !draft.startDate || !draft.endDate) {
      setImpact(null);
      setImpactMessage({ text: "Die betriebliche Auswirkung erscheint nach der Auswahl.", type: "" });
      return;
    }
    if (validationError || days === null) {
      setImpact(null);
      setImpactMessage({ text: validationError || "Im gewählten Zeitraum liegt kein Arbeitstag.", type: "error" });
      return;
    }

    let active = true;
    setImpactMessage({ text: "Auswirkung wird geprüft...", type: "" });
    previewVacationImpact(draft)
      .then((result) => {
        if (!active) return;
        setImpact(result.impact || null);
        setImpactMessage({ text: result.impact?.summary || "Keine auffälligen Konflikte erkannt.", type: "" });
      })
      .catch((error: unknown) => {
        if (!active) return;
        setImpact(null);
        setImpactMessage({ text: vacationErrorMessage(error), type: "error" });
      });

    return () => {
      active = false;
    };
  }, [draft, selectedBalance, validationError]);

  return (
    <>
      <PageHeader
        title="Urlaubsplanung"
        description="Anträge, Vertreter, Schichtbezug und Auswirkungen auf den Betrieb in einer Ansicht."
        actions={[
          { onClick: () => setIsRequestDrawerOpen(true), schema: createActionDefinition("vacationRequest"), variant: "primary" },
          { href: "#vacation-decisions", label: "Offene Anträge" }
        ]}
      />
      <StatStrip
        label="Urlaubskennzahlen"
        stats={[
          { label: "Ausstehend", value: pendingRequests.length, meta: "Anträge zur Entscheidung", tone: pendingRequests.length ? "warning" : "neutral" },
          {
            label: "Konflikte",
            value: requests.filter((request) => (
              ["pending", "approved"].includes(request.status || "") && ["warning", "critical"].includes(request.impact_level || "")
            )).length,
            meta: "Unterbesetzung oder Schichttreffer",
            tone: "danger"
          },
          { label: "Verfügbar", value: selectedBalance ? String(selectedBalance.available || 0) : "–", meta: "für die ausgewählte Person", tone: "success" },
          { label: "Genehmigt", value: summaries.reduce((sum, summary) => sum + Number(summary.used || 0), 0), meta: "genutzte Tage im Jahr" },
          { label: "Reserviert", value: summaries.reduce((sum, summary) => sum + Number(summary.pending || 0), 0), meta: "durch offene Anträge" }
        ]}
      />
      <section className="vacation-planning-grid" aria-label="Urlaubsplanung Workflow">
        <VacationPendingPanel
          onMessageChange={setMessage}
          onMutated={() => refreshVacationData(selectedYear)}
          onYearChange={setSelectedYear}
          pendingRequests={pendingRequests}
          selectedBalanceFor={selectedBalanceFor}
          selectedYear={selectedYear}
          user={user}
          yearOptions={yearOptions}
        />
      </section>
      <VacationOpsPanels
        filteredHistory={filteredHistory}
        filterStatus={filterStatus}
        onFilterStatusChange={setFilterStatus}
        onMessageChange={setMessage}
        onMutated={() => refreshVacationData(selectedYear)}
        requests={requests}
        selectedBalanceFor={selectedBalanceFor}
        summaries={summaries}
        user={user}
      />
      <ActionDrawer
        definition={createActionDefinition("vacationRequest")}
        isOpen={isRequestDrawerOpen}
        onClose={() => setIsRequestDrawerOpen(false)}
      >
        <VacationRequestPanel
          draft={draft}
          employees={employees}
          impact={impact}
          impactMessage={impactMessage}
          message={message}
          onDraftChange={updateDraft}
          onMessageChange={setMessage}
          onSaved={async () => {
            await refreshVacationData(selectedYear);
            setIsRequestDrawerOpen(false);
          }}
          selectedBalance={selectedBalance}
          selectedEmployee={selectedEmployee}
          submitDisabled={submitDisabled}
        />
      </ActionDrawer>
    </>
  );
}
