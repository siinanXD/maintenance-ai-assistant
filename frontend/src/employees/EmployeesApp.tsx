import { useEffect, useState, type ReactNode } from "react";

import { canWriteDashboard } from "../auth/permissions";
import { ActionDrawer } from "../components/ui/ActionDrawer";
import { createActionDefinition } from "../components/ui/createActionSchema";
import { PageHeader } from "../components/ui/PageHeader";
import { StatStrip } from "../components/ui/StatStrip";
import { loadEmployees } from "./employeeApi";
import { EmployeeEditDialog } from "./components/EmployeeEditDialog";
import { EmployeeFormPanel } from "./components/EmployeeFormPanel";
import { EmployeeList } from "./components/EmployeeList";
import type { Employee, EmployeeDraft, MessageState } from "./employeeTypes";
import { canManageEmployees, EMPTY_EMPLOYEE_DRAFT, employeeErrorMessage } from "./employeeUtils";

/**
 * Render the React employees workflow island.
 */
export function EmployeesApp(): ReactNode {
  const writable = canWriteDashboard("employees");
  const manageable = canManageEmployees(writable);
  const [isCreateDrawerOpen, setIsCreateDrawerOpen] = useState(false);
  const [createDraft, setCreateDraft] = useState<EmployeeDraft>({ ...EMPTY_EMPLOYEE_DRAFT });
  const [editingEmployee, setEditingEmployee] = useState<Employee | null>(null);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [message, setMessage] = useState<MessageState>({ text: "", error: false });

  /**
   * Refresh all visible employee rows.
   */
  async function refreshEmployees(): Promise<void> {
    setEmployees(await loadEmployees());
  }

  useEffect(() => {
    refreshEmployees().catch((error: unknown) => {
      setMessage({ text: employeeErrorMessage(error), error: true });
    });
    if (window.location.hash === "#employee-create") {
      setIsCreateDrawerOpen(true);
    }
  }, []);

  return (
    <>
      <PageHeader
        title="Mitarbeiter"
        description="Mitarbeiterdaten erfassen und Dokumente direkt an der Person ablegen."
        actions={[
          { hidden: !manageable, onClick: () => setIsCreateDrawerOpen(true), schema: createActionDefinition("employeeCreate"), variant: "primary" }
        ]}
      />
      <StatStrip
        label="Personalstatus"
        stats={[
          { label: "Mitarbeitende", value: employees.length, meta: "sichtbar für dich" },
          {
            label: "Abteilungen",
            value: new Set(employees.map((employee) => employee.department).filter(Boolean)).size,
            meta: "mit zugeordneten Personen"
          },
          {
            label: "Qualifiziert",
            value: employees.filter((employee) => Boolean(employee.qualifications?.trim())).length,
            meta: "mit hinterlegten Qualifikationen"
          }
        ]}
      />
      <section className="dashboard-grid">
        {!manageable && message.text ? (
          <section className="card app-card lg:col-span-12" role="status">
            <div className="card-body">
              <p className={`panel-meta${message.error ? " is-error" : ""}`}>{message.text}</p>
            </div>
          </section>
        ) : null}
        <EmployeeList
          employees={employees}
          manageable={manageable}
          onEdit={setEditingEmployee}
          onMessageChange={setMessage}
          onMutated={refreshEmployees}
        />
      </section>
      <EmployeeEditDialog
        employee={editingEmployee}
        onClose={() => setEditingEmployee(null)}
        onMessageChange={setMessage}
        onSaved={refreshEmployees}
      />
      <ActionDrawer
        definition={createActionDefinition("employeeCreate")}
        isOpen={isCreateDrawerOpen}
        onClose={() => setIsCreateDrawerOpen(false)}
      >
        <EmployeeFormPanel
          drawerMode
          draft={createDraft}
          hidden={!manageable}
          message={message}
          onDraftChange={setCreateDraft}
          onMessageChange={setMessage}
          onSaved={async () => {
            await refreshEmployees();
            setIsCreateDrawerOpen(false);
          }}
        />
      </ActionDrawer>
    </>
  );
}
