import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { canWriteDashboard } from "../../auth/permissions";
import { type DashboardPayload, type DashboardTaskMutation, type DashboardTaskReportPayload } from "../dashboardApi";
import {
  editStateFromTask,
  initialReportState,
  REPORT_FIELDS,
  ReportField,
  TaskDetailRows,
  TaskEditForm,
  type EditState,
  type ReportState,
  type ReportTextFieldName
} from "./DashboardTaskDetailFields";
import { taskDepartmentName, taskText } from "../dashboardTaskModel";

type DashboardTaskDetailModalProps = {
  readonly activeTask: DashboardPayload | null;
  readonly isBusy: boolean;
  readonly message: string;
  readonly onClose: () => void;
  readonly onComplete: (payload: DashboardTaskReportPayload) => void;
  readonly onStart: () => void;
  readonly onUpdate: (payload: DashboardTaskMutation) => void;
};

/**
 * Render the task detail modal controlled by the React dashboard runtime.
 */
export function DashboardTaskDetailModal({
  activeTask,
  isBusy,
  message,
  onClose,
  onComplete,
  onStart,
  onUpdate
}: DashboardTaskDetailModalProps): ReactNode {
  const [reportState, setReportState] = useState<ReportState>(initialReportState);
  const [editState, setEditState] = useState<EditState>(() => editStateFromTask(activeTask));
  const canWriteTasks = canWriteDashboard("tasks");
  const status = taskText(activeTask, "status", "open");

  useEffect(() => {
    setReportState(initialReportState());
    setEditState(editStateFromTask(activeTask));
  }, [activeTask]);

  /**
   * Update one report field.
   */
  function updateReportField(fieldName: ReportTextFieldName, value: string): void {
    setReportState((currentState) => ({ ...currentState, [fieldName]: value }));
  }

  /**
   * Update one edit field.
   */
  function updateEditField(fieldName: keyof EditState, value: string): void {
    setEditState((currentState) => ({ ...currentState, [fieldName]: value }));
  }

  /**
   * Submit the edit form through the React dashboard action handler.
   */
  function submitEditForm(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    onUpdate(editState);
  }

  /**
   * Submit the completion action with optional report data.
   */
  function completeTask(): void {
    onComplete(reportState.generate_report ? { ...reportState, notes: reportState.action } : {});
  }

  return (
    <div className="modal task-detail-modal" hidden={!activeTask}>
      <div className="modal-box max-w-4xl">
        <div className="panel-header">
          <div>
            <h2 className="panel-title" id="task-detail-title">
              {taskText(activeTask, "title", "Aufgabe")}
            </h2>
            <p className="panel-meta">
              {activeTask ? taskDepartmentName(activeTask) : "Details und Workflow"}
            </p>
          </div>
          <button className="btn btn-ghost btn-sm" type="button" onClick={onClose}>
            Schließen
          </button>
        </div>
        <div className="task-detail-body">
          <TaskDetailRows task={activeTask} />
          {activeTask && canWriteTasks ? (
            <TaskEditForm
              editState={editState}
              isBusy={isBusy}
              onChange={updateEditField}
              onSubmit={submitEditForm}
            />
          ) : null}
        </div>
        <div className="form-grid mt-6">
          <label className="field cursor-pointer">
            <span>Wartungsbericht erzeugen</span>
            <input
              className="checkbox checkbox-primary"
              type="checkbox"
              checked={reportState.generate_report}
              onChange={(event) =>
                setReportState((currentState) => ({
                  ...currentState,
                  generate_report: event.target.checked
                }))
              }
            />
          </label>
          {REPORT_FIELDS.map((field) => (
            <ReportField
              key={field.id}
              field={field}
              value={String(reportState[field.fieldName] || "")}
              onChange={updateReportField}
            />
          ))}
        </div>
        <div className="toolbar form-actions">
          <button
            className="btn btn-primary"
            disabled={isBusy || !canWriteTasks || status !== "open"}
            type="button"
            onClick={onStart}
          >
            Aufgabe starten
          </button>
          <button
            className="btn btn-success text-white"
            disabled={isBusy || !canWriteTasks || status === "done" || status === "cancelled"}
            type="button"
            onClick={completeTask}
          >
            Aufgabe abschließen
          </button>
          <span className="panel-meta" role="status" aria-live="polite">
            {message}
          </span>
        </div>
      </div>
    </div>
  );
}
