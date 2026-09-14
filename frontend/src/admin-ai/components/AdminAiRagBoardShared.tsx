import { type ChangeEvent, type FormEvent, type MouseEvent, type ReactNode } from "react";
import { type AdminAiPayload } from "../adminAiApi";
import { type AdminAiRagBoardFilters, type AdminAiTrainingForm, QUALITY_STATUSES } from "../adminAiRagBoardModel";
import { qualityStatusLabel } from "../adminAiRagLabels";

export const QUALITY_OPTIONS = [
  ["", "Alle Qualitätsstatus"],
  ...QUALITY_STATUSES.map((status) => [status, qualityStatusLabel(status)] as const)
] as const;

export const SOURCE_OPTIONS = [
  ["", "Alle Quellen"],
  ["upload", "Hochladungen"],
  ["manual_training", "Manuelles Training"],
  ["generated_document", "Berichte"],
  ["error_entry", "Fehlerkatalog"],
  ["task", "Aufgaben"],
  ["machine", "Maschinen"],
  ["inventory_material", "Inventar"],
  ["maintenance_plan", "Wartungspläne"],
  ["machine_manual", "Maschinenhandbücher"],
  ["shift_handover", "Schichtübergaben"]
] as const;

/**
 * Return true when an unknown value is an object payload.
 */
export function isPayload(value: unknown): value is AdminAiPayload {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Return an input change handler for filter state.
 */
export function filterChange(
  onChange: (key: keyof AdminAiRagBoardFilters, value: string) => void,
  key: keyof AdminAiRagBoardFilters
) {
  return (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => onChange(key, event.target.value);
}

/**
 * Return an input change handler for the training form.
 */
export function formChange(
  form: AdminAiTrainingForm,
  onChange: (form: AdminAiTrainingForm) => void,
  key: keyof AdminAiTrainingForm
) {
  return (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    onChange({ ...form, [key]: event.target.value });
  };
}

/**
 * Submit the training editor form through the React handler.
 */
export function submitTraining(
  event: FormEvent<HTMLFormElement>,
  onSaveTraining: (form: AdminAiTrainingForm) => void,
  form: AdminAiTrainingForm
): void {
  event.preventDefault();
  onSaveTraining(form);
}

/**
 * Submit the knowledge upload form through the React handler.
 */
export function submitUpload(
  event: FormEvent<HTMLFormElement>,
  onKnowledgeUpload: (form: HTMLFormElement) => void
): void {
  event.preventDefault();
  onKnowledgeUpload(event.currentTarget);
}

/**
 * Read the selected quality status next to the clicked button.
 */
export function onUpdateQualityClick(
  event: MouseEvent<HTMLButtonElement>,
  onUpdateKnowledgeQuality: (documentId: number, qualityStatus: string) => void,
  documentId: number
): void {
  const row = event.currentTarget.closest("tr");
  const select = row?.querySelector<HTMLSelectElement>("[data-knowledge-quality-select]");
  onUpdateKnowledgeQuality(documentId, select?.value || "draft");
}

/**
 * Render a select filter.
 */
export function SelectFilter({
  ariaLabel,
  onChange,
  options,
  value
}: {
  readonly ariaLabel?: string;
  readonly onChange: (event: ChangeEvent<HTMLSelectElement>) => void;
  readonly options: readonly (readonly [string, string])[];
  readonly value: string;
}): ReactNode {
  return (
    <select className="input input-bordered" aria-label={ariaLabel} value={value} onChange={onChange}>
      {options.map(([optionValue, label]) => (
        <option key={optionValue} value={optionValue}>{label}</option>
      ))}
    </select>
  );
}
