import { useMemo, useState, type ChangeEvent, type ReactNode } from "react";

import { confirmAction } from "../../app/runtimeBridge";
import { deleteEmployee, uploadEmployeeDocument } from "../employeeApi";
import type { Employee, EmployeeDocument, MessageState } from "../employeeTypes";
import {
  employeeErrorMessage,
  employeeSearchText,
  qualificationLabels,
  triggerEmployeeDocumentDownload
} from "../employeeUtils";

type EmployeeListProps = {
  readonly employees: readonly Employee[];
  readonly manageable: boolean;
  readonly onEdit: (employee: Employee) => void;
  readonly onMessageChange: (message: MessageState) => void;
  readonly onMutated: () => Promise<void>;
};

/**
 * Render one metadata cell for an employee card.
 */
function EmployeeMetaCell({ label, value }: { readonly label: string; readonly value?: string | null }): ReactNode {
  if (!value) return null;
  return (
    <div className="resource-metric">
      <span className="resource-label">{label}</span>
      <span className="resource-value">{value}</span>
    </div>
  );
}

/**
 * Render document download actions for one employee.
 */
function EmployeeDocumentActions(props: {
  readonly documents: readonly EmployeeDocument[];
  readonly onMessageChange: (message: MessageState) => void;
}): ReactNode {
  /**
   * Download one employee document.
   */
  function downloadDocument(documentItem: EmployeeDocument): void {
    const downloaded = triggerEmployeeDocumentDownload(
      documentItem.download_url,
      documentItem.original_filename
    );
    if (!downloaded) {
      props.onMessageChange({ text: "Dokument konnte nicht heruntergeladen werden.", error: true });
    }
  }

  return (
    <div className="resource-actions">
      {props.documents.length ? props.documents.map((documentItem) => (
        <button
          className="btn btn-link btn-xs px-0 justify-start"
          key={documentItem.id}
          type="button"
          onClick={() => downloadDocument(documentItem)}
        >
          {documentItem.original_filename || "Dokument"}
        </button>
      )) : <span className="panel-meta text-xs">Keine Dokumente</span>}
    </div>
  );
}

/**
 * Render upload, edit and delete actions for one employee.
 */
function EmployeeManageActions(props: {
  readonly employee: Employee;
  readonly onEdit: (employee: Employee) => void;
  readonly onMessageChange: (message: MessageState) => void;
  readonly onMutated: () => Promise<void>;
}): ReactNode {
  const [uploading, setUploading] = useState(false);

  /**
   * Upload selected files for one employee.
   */
  async function uploadDocuments(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const files = Array.from(event.currentTarget.files || []);
    if (!files.length) return;

    setUploading(true);
    props.onMessageChange({ text: "Dokumente werden hochgeladen...", error: false });
    try {
      for (const file of files) {
        await uploadEmployeeDocument(props.employee.id, file);
      }
      event.currentTarget.value = "";
      await props.onMutated();
      props.onMessageChange({
        text: files.length === 1 ? "Dokument hochgeladen." : `${files.length} Dokumente hochgeladen.`,
        error: false
      });
    } catch (error) {
      props.onMessageChange({ text: employeeErrorMessage(error), error: true });
    } finally {
      setUploading(false);
    }
  }

  /**
   * Delete one employee after confirmation.
   */
  async function removeEmployee(): Promise<void> {
    if (!(await confirmAction({ title: "Mitarbeiter löschen", message: `${props.employee.name || "Mitarbeiter"} wirklich löschen?`, confirmText: "Löschen" }))) return;
    try {
      await deleteEmployee(props.employee.id);
      await props.onMutated();
      props.onMessageChange({ text: "Mitarbeiter gelöscht.", error: false });
    } catch (error) {
      props.onMessageChange({ text: employeeErrorMessage(error), error: true });
    }
  }

  return (
    <>
      <div className="resource-upload">
        <input disabled={uploading} multiple type="file" onChange={uploadDocuments} />
      </div>
      <div className="table-actions">
        <button className="btn btn-outline btn-sm" type="button" onClick={() => props.onEdit(props.employee)}>Bearbeiten</button>
        <button className="btn btn-ghost btn-sm" type="button" onClick={removeEmployee}>Löschen</button>
      </div>
    </>
  );
}

/**
 * Render one employee resource card.
 */
function EmployeeCard(props: EmployeeListProps & { readonly employee: Employee }): ReactNode {
  const documents = props.employee.documents || [];
  const qualifications = qualificationLabels(props.employee.qualifications);

  return (
    <article className="resource-card">
      <div className="resource-card-header">
        <div>
          <h3 className="resource-card-title">{props.employee.name || "Unbenannter Mitarbeiter"}</h3>
          <p className="resource-card-subtitle">{props.employee.personnel_number || "-"}</p>
        </div>
        <div className="resource-card-badges">
          {props.employee.department ? <span className="badge badge-neutral">{props.employee.department}</span> : null}
          {props.employee.team ? <span className="badge badge-info">Team {props.employee.team}</span> : null}
        </div>
      </div>
      <div className="resource-meta-grid">
        <EmployeeMetaCell label="Schichtmodell" value={props.employee.shift_model} />
        <EmployeeMetaCell label="Schicht" value={props.employee.current_shift} />
        <EmployeeMetaCell label="Gehaltsklasse" value={props.employee.salary_group} />
        <EmployeeMetaCell label="Lieblingsmaschine" value={props.employee.favorite_machine} />
      </div>
      <div className="badge-list">
        {qualifications.map((qualification) => (
          <span className="badge badge-sm badge-outline" key={qualification}>{qualification}</span>
        ))}
      </div>
      <EmployeeDocumentActions documents={documents} onMessageChange={props.onMessageChange} />
      {props.manageable ? (
        <EmployeeManageActions
          employee={props.employee}
          onEdit={props.onEdit}
          onMessageChange={props.onMessageChange}
          onMutated={props.onMutated}
        />
      ) : null}
    </article>
  );
}

/**
 * Render the searchable employee overview.
 */
export function EmployeeList(props: EmployeeListProps): ReactNode {
  const [search, setSearch] = useState("");
  const visibleEmployees = useMemo(() => {
    const query = search.trim().toLowerCase();
    return query ? props.employees.filter((employee) => employeeSearchText(employee).includes(query)) : props.employees;
  }, [props.employees, search]);

  return (
    <article className="card app-card mobile-primary-card lg:col-span-12">
      <div className="card-body">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Mitarbeiterübersicht</h2>
            <p className="panel-meta">Schicht, Qualifikationen und Dokumentenstatus pro Person</p>
          </div>
          <span className="badge badge-status is-open">{props.employees.length} Mitarbeitende</span>
        </div>
        <div className="list-toolbar">
          <label className="compact-search-field" htmlFor="employee-list-search">
            <span>Mitarbeiter suchen</span>
            <input
              className="input input-bordered input-sm"
             
              id="employee-list-search"
              placeholder="Name, Team, Schicht, Qualifikation"
              value={search}
              onChange={(event) => setSearch(event.currentTarget.value)}
            />
          </label>
        </div>
        <div className="resource-card-grid employee-card-grid bounded-list-scroll">
          {visibleEmployees.length ? visibleEmployees.map((employee) => (
            <EmployeeCard {...props} employee={employee} key={employee.id} />
          )) : <div className="empty-state">Keine Mitarbeiter vorhanden.</div>}
        </div>
      </div>
    </article>
  );
}
