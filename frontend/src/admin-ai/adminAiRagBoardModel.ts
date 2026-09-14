import { listData } from "../api/payload";
import { safeErrorMessage } from "../utils/errors";
import { type AdminAiPayload } from "./adminAiApi";
import { numberText } from "./adminAiFormat";
import { type AdminAiSourceCheckState } from "./adminAiSourceCheckModel";

export type AdminAiRagBoardFilters = {
  readonly knowledgeQuality: string;
  readonly knowledgeQuery: string;
  readonly knowledgeSource: string;
  readonly knowledgeStatus: string;
  readonly networkFocus: string;
  readonly networkFocusType: string;
  readonly networkQuality: string;
  readonly networkQuery: string;
  readonly networkSource: string;
  readonly trainingActive: string;
  readonly trainingQuery: string;
};

export type AdminAiTrainingForm = {
  readonly answer: string;
  readonly category: string;
  readonly department: string;
  readonly id: string;
  readonly isActive: boolean;
  readonly keywords: string;
  readonly priority: string;
  readonly question: string;
  readonly title: string;
};

export type AdminAiRagBoardState = {
  readonly errorMessage: string;
  readonly filters: AdminAiRagBoardFilters;
  readonly isLoading: boolean;
  readonly isSaving: boolean;
  readonly jobs: readonly AdminAiPayload[];
  readonly knowledge: readonly AdminAiPayload[];
  readonly knowledgeStatus: AdminAiPayload | null;
  readonly network: AdminAiPayload | null;
  readonly statusMessage: string;
  readonly training: readonly AdminAiPayload[];
  readonly trainingForm: AdminAiTrainingForm;
};

const EMPTY_RAG_BOARD_FILTERS: AdminAiRagBoardFilters = {
  knowledgeQuality: "",
  knowledgeQuery: "",
  knowledgeSource: "",
  knowledgeStatus: "",
  networkFocus: "",
  networkFocusType: "",
  networkQuality: "",
  networkQuery: "",
  networkSource: "",
  trainingActive: "",
  trainingQuery: ""
};

export const EMPTY_TRAINING_FORM: AdminAiTrainingForm = {
  answer: "",
  category: "",
  department: "",
  id: "",
  isActive: true,
  keywords: "",
  priority: "50",
  question: "",
  title: ""
};

export const EMPTY_ADMIN_AI_RAG_BOARD_STATE: AdminAiRagBoardState = {
  errorMessage: "",
  filters: EMPTY_RAG_BOARD_FILTERS,
  isLoading: false,
  isSaving: false,
  jobs: [],
  knowledge: [],
  knowledgeStatus: null,
  network: null,
  statusMessage: "",
  training: [],
  trainingForm: EMPTY_TRAINING_FORM
};

export const QUALITY_STATUSES = [
  "draft",
  "ai_suggested",
  "technician_confirmed",
  "admin_approved",
  "low_quality",
  "duplicate",
  "outdated",
  "rejected"
] as const;

export const RAG_SOURCE_DEFINITIONS = [
  {
    description: "Uploads, Berichte und Maschinenhandbücher",
    icon: "D",
    key: "documents",
    label: "Dokumente",
    types: ["upload", "generated_document", "machine_manual", "maintenance_plan"]
  },
  {
    description: "Freigegebene Fragen und Antworten",
    icon: "F",
    key: "faq",
    label: "FAQ",
    types: ["faq"]
  },
  {
    description: "Manuelles Assistant-Training",
    icon: "T",
    key: "training",
    label: "Trainingswissen",
    types: ["manual_training"]
  },
  {
    description: "Fehlercodes, Ursachen und Lösungen",
    icon: "!",
    key: "error_catalog",
    label: "Fehlerkatalog",
    types: ["error_entry"]
  },
  {
    description: "Wartungs- und Eskalationsaufgaben",
    icon: "A",
    key: "tasks",
    label: "Aufgaben",
    types: ["task"]
  },
  {
    description: "Anlagen, Komponenten und Maschinenkontext",
    icon: "M",
    key: "machines",
    label: "Maschinen",
    types: ["machine"]
  }
] as const;

export type AdminAiRagBoardProps = {
  readonly onCreateFaq: () => void;
  readonly onDeleteKnowledge: (documentId: number) => void;
  readonly onDeleteTraining: (entryId: number) => void;
  readonly onFeedback: (rating: string, comment?: string) => void;
  readonly onKnowledgeFilterChange: (key: keyof AdminAiRagBoardFilters, value: string) => void;
  readonly onKnowledgeUpload: (form: HTMLFormElement) => void;
  readonly onNetworkFilterChange: (key: keyof AdminAiRagBoardFilters, value: string) => void;
  readonly onQueueDocument: (documentId: number) => void;
  readonly onQueueStale: () => void;
  readonly onReindexAll: () => void;
  readonly onReindexDocument: (documentId: number) => void;
  readonly onReindexStale: () => void;
  readonly onReset: () => void;
  readonly onSaveTraining: (form: AdminAiTrainingForm) => void;
  readonly onSelectTraining: (entry: Record<string, unknown>) => void;
  readonly onSourceTestSubmit: (form: HTMLFormElement, intent?: string) => void;
  readonly onTrainingFilterChange: (key: keyof AdminAiRagBoardFilters, value: string) => void;
  readonly onTrainingFormChange: (form: AdminAiTrainingForm) => void;
  readonly onUpdateKnowledgeQuality: (documentId: number, qualityStatus: string) => void;
  readonly ragBoardState: AdminAiRagBoardState;
  readonly sourceCheckState: AdminAiSourceCheckState;
};

/**
 * Return an object from an unknown payload.
 */
export function objectPayload(value: unknown): AdminAiPayload {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as AdminAiPayload)
    : {};
}

/**
 * Return a string fallback for visible UI values.
 */
export function ragText(value: unknown, fallback = "-"): string {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

/**
 * Return list items from an Admin-AI response.
 */
export function ragItems(payload: unknown): AdminAiPayload[] {
  return listData<AdminAiPayload>(payload);
}

/**
 * Resolve a safe RAG Board error state.
 */
export function failedRagBoardState(error: unknown): Pick<AdminAiRagBoardState, "errorMessage"> {
  return { errorMessage: safeErrorMessage(error, "RAG Board konnte nicht geladen werden.") };
}

/**
 * Build the query string for knowledge documents.
 */
export function knowledgeQueryString(filters: AdminAiRagBoardFilters): string {
  return new URLSearchParams({
    limit: "50",
    q: filters.knowledgeQuery,
    quality_status: filters.knowledgeQuality,
    source_type: filters.knowledgeSource,
    status: filters.knowledgeStatus
  }).toString();
}

/**
 * Build the query string for manual training entries.
 */
export function trainingQueryString(filters: AdminAiRagBoardFilters): string {
  return new URLSearchParams({
    active: filters.trainingActive,
    limit: "50",
    q: filters.trainingQuery
  }).toString();
}

/**
 * Build the query string for the knowledge network.
 */
export function networkQueryString(filters: AdminAiRagBoardFilters): string {
  return new URLSearchParams({
    focus: filters.networkFocus,
    focus_type: filters.networkFocusType,
    limit: "120",
    q: filters.networkQuery,
    quality_status: filters.networkQuality,
    source_type: filters.networkSource
  }).toString();
}

/**
 * Return a prompt-safe job result summary.
 */
export function safeJobResultText(job: AdminAiPayload): string {
  if (job.status === "failed") return "Fehlerdetails ausgeblendet";
  const result = objectPayload(job.result);
  if (result.indexed != null || result.chunks != null) {
    return `Indexiert: ${numberText(result.indexed || 0)} / Textabschnitte: ${numberText(result.chunks || 0)}`;
  }
  if (job.status === "done") return "abgeschlossen";
  if (job.status === "running") return "läuft";
  if (job.status === "queued") return "wartet";
  return "-";
}

/**
 * Normalize a training form into an API payload.
 */
export function trainingPayload(form: AdminAiTrainingForm): Record<string, unknown> {
  return {
    answer: form.answer.trim(),
    category: form.category.trim() || "wartung",
    department: form.department.trim(),
    is_active: form.isActive,
    keywords: form.keywords.trim(),
    priority: Number(form.priority || 50),
    question: form.question.trim(),
    title: form.title.trim()
  };
}

/**
 * Convert one API training entry into the editor form shape.
 */
export function trainingFormFromEntry(entry: AdminAiPayload): AdminAiTrainingForm {
  return {
    answer: ragText(entry.answer, ""),
    category: ragText(entry.category, ""),
    department: ragText(entry.department, ""),
    id: ragText(entry.id, ""),
    isActive: Boolean(entry.is_active),
    keywords: ragText(entry.keywords, ""),
    priority: ragText(entry.priority, "50"),
    question: ragText(entry.question, ""),
    title: ragText(entry.title, "")
  };
}
