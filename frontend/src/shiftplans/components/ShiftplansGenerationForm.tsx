import { type ReactNode } from "react";

import type { Machine, ShiftModel, ShiftplansMessage, ShiftplanDraft } from "../shiftplanTypes";
import { beginnerModelLabel, rotationLabel, shiftSummary } from "../shiftplanUtils";

type DepartmentOption = {
  readonly label: string;
  readonly value: string;
};

type ShiftplansGenerationFormProps = {
  readonly busyAction: "generate" | "preview" | null;
  readonly draft: ShiftplanDraft;
  readonly machines: readonly Machine[];
  readonly message: ShiftplansMessage;
  readonly models: readonly ShiftModel[];
  readonly onDraftChange: (draft: ShiftplanDraft) => void;
  readonly onGenerate: () => void;
  readonly onMachineToggle: (machineId: number, checked: boolean) => void;
  readonly onPreview: () => void;
  readonly selectedMachineIds: ReadonlySet<number>;
  readonly writable: boolean;
};

const DEPARTMENT_OPTIONS: readonly DepartmentOption[] = [
  { label: "Produktion", value: "Produktion" },
  { label: "Instandhaltung", value: "Instandhaltung" },
  { label: "Verwaltung", value: "Verwaltung" },
  { label: "IT", value: "IT" },
  { label: "Personalabteilung", value: "Personalabteilung" },
];

/**
 * Render the selected shift model preview.
 */
function ShiftModelPreview({ model }: { readonly model: ShiftModel | null }): ReactNode {
  return (
    <section className="sp-model-preview" id="sp-model-preview" aria-live="polite" hidden={!model}>
      <div>
        <p className="stat-label mb-1">Modellvorschau</p>
        <h3 className="panel-title" id="sp-model-title">
          {model ? beginnerModelLabel(model) : "Schichtmodell"}
        </h3>
        <p className="panel-meta" id="sp-model-description">
          {model?.description || ""}
        </p>
      </div>
      <dl className="sp-model-preview-grid">
        <div>
          <dt>Schichten</dt>
          <dd id="sp-model-shifts">{model ? shiftSummary(model) : "-"}</dd>
        </div>
        <div>
          <dt>Teams</dt>
          <dd id="sp-model-team-count">{model?.team_count || "-"}</dd>
        </div>
        <div>
          <dt>Wochenende</dt>
          <dd id="sp-model-weekend">
            {model ? model.weekend_label || (model.weekend_operation ? "Wochenendbetrieb aktiv" : "Montag bis Freitag") : "-"}
          </dd>
        </div>
        <div>
          <dt>Rotation</dt>
          <dd id="sp-model-rotation">{model ? model.rotation_label || rotationLabel(model.rotation_direction) : "-"}</dd>
        </div>
        <div>
          <dt>Ruhezeit</dt>
          <dd id="sp-model-rest">{model ? `${model.recommended_rest_hours || 11} Stunden empfohlen` : "-"}</dd>
        </div>
      </dl>
    </section>
  );
}

/**
 * Render selected machines as checkbox options.
 */
function MachinePicker({
  machines,
  onMachineToggle,
  selectedMachineIds,
}: Pick<ShiftplansGenerationFormProps, "machines" | "onMachineToggle" | "selectedMachineIds">): ReactNode {
  if (!machines.length) {
    return (
      <div className="sp-machine-picker" id="sp-machine-picker" aria-live="polite">
        <p className="panel-meta">Maschinen werden geladen...</p>
      </div>
    );
  }

  return (
    <div className="sp-machine-picker" id="sp-machine-picker" aria-live="polite">
      {machines.map((machine) => (
        <label className="sp-machine-option" key={machine.id}>
          <input
            type="checkbox"
            value={machine.id}
            checked={selectedMachineIds.has(machine.id)}
            onChange={(event) => onMachineToggle(machine.id, event.currentTarget.checked)}
          />
          <span>
            {machine.name} ({machine.required_employees || 1} MA)
          </span>
        </label>
      ))}
    </div>
  );
}

/**
 * Render the generation form controlled by React.
 */
export function ShiftplansGenerationForm({
  busyAction,
  draft,
  machines,
  message,
  models,
  onDraftChange,
  onGenerate,
  onMachineToggle,
  onPreview,
  selectedMachineIds,
  writable,
}: ShiftplansGenerationFormProps): ReactNode {
  const selectedModel = models.find((model) => model.key === draft.shiftModelKey) || null;

  if (!writable) return null;

  return (
    <details
      className="card app-card mobile-action-section lg:col-span-12 no-print"
     
     
      open
    >
      <summary className="mobile-action-summary">
        <span>
          <span className="mobile-action-title">Schichtplan generieren</span>
          <span className="mobile-action-meta">Abteilung, Zeitraum und Präferenzen</span>
        </span>
      </summary>
      <form id="sp-form">
        <div className="card-body">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Schichtplan generieren</h2>
              <p className="panel-meta">ArbZG: max. 10h/Schicht · 11h Ruhezeit · faire Verteilung</p>
            </div>
            <span className="badge badge-info badge-outline">KI</span>
          </div>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="sp-department">Abteilung *</label>
              <select
                className="select select-bordered"
                id="sp-department"
                required
                value={draft.department}
                onChange={(event) => onDraftChange({ ...draft, department: event.currentTarget.value })}
              >
                <option value="" disabled>
                  Bitte wählen...
                </option>
                {DEPARTMENT_OPTIONS.map((department) => (
                  <option key={department.value} value={department.value}>
                    {department.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="sp-title">Titel</label>
              <input
                className="input input-bordered"
                id="sp-title"
                placeholder="Schichtplan KW 22"
                value={draft.title}
                onChange={(event) => onDraftChange({ ...draft, title: event.currentTarget.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="sp-start">Startdatum *</label>
              <input
                className="input input-bordered"
                id="sp-start"
                type="date"
                required
                value={draft.startDate}
                onChange={(event) => onDraftChange({ ...draft, startDate: event.currentTarget.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="sp-days">Tage</label>
              <input
                className="input input-bordered"
                id="sp-days"
                type="number"
                min="1"
                max="31"
                value={draft.days}
                onChange={(event) => onDraftChange({ ...draft, days: event.currentTarget.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="sp-shift-model">Schichtmodell *</label>
              <select
                className="select select-bordered"
                id="sp-shift-model"
                required
                value={draft.shiftModelKey}
                onChange={(event) => onDraftChange({ ...draft, shiftModelKey: event.currentTarget.value })}
              >
                <option value="" disabled>
                  Bitte Schichtmodell wählen
                </option>
                {models.map((model) => (
                  <option key={model.key} value={model.key}>
                    {beginnerModelLabel(model)}
                  </option>
                ))}
              </select>
              <input id="sp-rhythm" type="hidden" value={selectedModel?.display_name || selectedModel?.name || selectedModel?.key || ""} readOnly />
            </div>
            <div className="field is-full">
              <ShiftModelPreview model={selectedModel} />
            </div>
            <div className="field is-full">
              <label>Maschinen *</label>
              <MachinePicker machines={machines} onMachineToggle={onMachineToggle} selectedMachineIds={selectedMachineIds} />
            </div>
            <div className="field is-full">
              <label htmlFor="sp-preferences">Präferenzen</label>
              <textarea
                className="textarea textarea-bordered"
                id="sp-preferences"
                rows={2}
                placeholder="Wünsche, Sperrtage, Teamregeln"
                value={draft.preferences}
                onChange={(event) => onDraftChange({ ...draft, preferences: event.currentTarget.value })}
              />
            </div>
            <div className="field is-full">
              <label htmlFor="sp-vacations">
                Urlaub <span className="stat-label">(Mitarbeiter-ID, Datum - eine Zeile je Eintrag)</span>
              </label>
              <textarea
                className="textarea textarea-bordered"
                id="sp-vacations"
                rows={2}
                placeholder="12, 2026-05-04, Urlaub"
                value={draft.vacations}
                onChange={(event) => onDraftChange({ ...draft, vacations: event.currentTarget.value })}
              />
            </div>
          </div>
          <div className="toolbar form-actions">
            <button className="btn btn-ghost" id="sp-preview-btn" type="button" disabled={busyAction !== null} onClick={onPreview}>
              {busyAction === "preview" ? "Vorschau läuft..." : "Vorschau prüfen"}
            </button>
            <button className="btn btn-primary" id="sp-submit-btn" type="button" disabled={busyAction !== null} onClick={onGenerate}>
              {busyAction === "generate" ? "Generiert..." : "Plan generieren"}
            </button>
            <span className={`panel-meta${message.isError ? " text-error" : ""}`} id="sp-msg" role="status" aria-live="polite">
              {message.text}
            </span>
          </div>
        </div>
      </form>
    </details>
  );
}
