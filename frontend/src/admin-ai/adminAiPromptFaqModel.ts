import { safeErrorMessage } from "../utils/errors";
import { type AdminAiPayload } from "./adminAiApi";

type AdminAiPromptVersion = {
  readonly id?: unknown;
  readonly status?: unknown;
  readonly version?: unknown;
};

export type AdminAiPromptTemplate = {
  readonly id?: unknown;
  readonly name?: unknown;
  readonly purpose?: unknown;
  readonly response_mode?: unknown;
  readonly versions?: readonly AdminAiPromptVersion[];
  readonly workflow_key?: unknown;
};

export type AdminAiFaqEntry = {
  readonly category?: unknown;
  readonly id?: unknown;
  readonly question?: unknown;
  readonly source?: unknown;
  readonly status?: unknown;
};

export type AdminAiFaqSuggestion = {
  readonly count?: unknown;
  readonly occurrence_count?: unknown;
  readonly question?: unknown;
};

export type AdminAiResponseSnippet = {
  readonly category?: unknown;
  readonly is_active?: unknown;
  readonly title?: unknown;
};

export type AdminAiPromptFaqState = {
  readonly errorMessage: string;
  readonly faqEntries: readonly AdminAiFaqEntry[];
  readonly frequentQuestions: readonly AdminAiFaqSuggestion[];
  readonly isLoading: boolean;
  readonly isSaving: boolean;
  readonly knowledgeGaps: readonly AdminAiFaqSuggestion[];
  readonly promptFormStatus: string;
  readonly prompts: readonly AdminAiPromptTemplate[];
  readonly responseSnippets: readonly AdminAiResponseSnippet[];
  readonly statusMessage: string;
};

export const EMPTY_ADMIN_AI_PROMPT_FAQ_STATE: AdminAiPromptFaqState = {
  errorMessage: "",
  faqEntries: [],
  frequentQuestions: [],
  isLoading: true,
  isSaving: false,
  knowledgeGaps: [],
  promptFormStatus: "",
  prompts: [],
  responseSnippets: [],
  statusMessage: ""
};

/**
 * Return true when a payload is an object.
 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Return a list field from a payload.
 */
function listField<TItem>(source: AdminAiPayload | null, key: string): TItem[] {
  const value = source?.[key];
  return Array.isArray(value) ? (value as TItem[]) : [];
}

/**
 * Convert unknown UI values into stable display text.
 */
export function promptFaqText(value: unknown, fallback = "-"): string {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

/**
 * Convert unknown count values into display text.
 */
function countText(value: unknown): string {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed.toLocaleString("de-DE") : promptFaqText(value);
}

/**
 * Extract prompt templates from the API payload.
 */
export function promptTemplates(payload: AdminAiPayload | null): AdminAiPromptTemplate[] {
  return listField<AdminAiPromptTemplate>(payload, "items");
}

/**
 * Extract FAQ entries from the API payload.
 */
export function faqEntries(payload: AdminAiPayload | null): AdminAiFaqEntry[] {
  return listField<AdminAiFaqEntry>(payload, "items");
}

/**
 * Extract FAQ suggestions from the API payload.
 */
export function faqSuggestions(payload: AdminAiPayload | null): {
  readonly frequentQuestions: AdminAiFaqSuggestion[];
  readonly knowledgeGaps: AdminAiFaqSuggestion[];
} {
  return {
    frequentQuestions: listField<AdminAiFaqSuggestion>(payload, "frequent_questions"),
    knowledgeGaps: listField<AdminAiFaqSuggestion>(payload, "knowledge_gaps")
  };
}

/**
 * Extract response snippets from the API payload.
 */
export function responseSnippets(payload: AdminAiPayload | null): AdminAiResponseSnippet[] {
  return listField<AdminAiResponseSnippet>(payload, "items");
}

/**
 * Return the active version for a prompt template.
 */
export function activePromptVersion(template: AdminAiPromptTemplate): AdminAiPromptVersion | null {
  const versions = Array.isArray(template.versions) ? template.versions : [];
  return versions.find((version) => version.status === "active") ?? null;
}

/**
 * Return a CSS class for an Admin-AI status pill.
 */
export function statusTone(status: unknown): "is-active" | "is-muted" | "is-stale" {
  if (status === "active" || status === "approved") return "is-active";
  if (status === "archived") return "is-muted";
  return "is-stale";
}

/**
 * Return the row value for one FAQ suggestion.
 */
export function suggestionCountText(item: AdminAiFaqSuggestion): string {
  return item.count !== undefined ? `${countText(item.count)}x` : `${countText(item.occurrence_count)}x`;
}

/**
 * Return a validated numeric id from an unknown API value.
 */
export function numericId(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

/**
 * Convert form entries into a plain object for JSON APIs.
 */
export function formPayload(form: HTMLFormElement): Record<string, unknown> {
  return Object.fromEntries(new FormData(form).entries());
}

/**
 * Return a safe error message for the Prompt & FAQ route.
 */
export function failedPromptFaqState(error: unknown): Pick<AdminAiPromptFaqState, "errorMessage"> {
  return {
    errorMessage: safeErrorMessage(error, "Prompt & FAQ konnte nicht komplett geladen werden.")
  };
}

/**
 * Return a safe API payload when a settled promise was fulfilled.
 */
export function settledPayload(result: PromiseSettledResult<AdminAiPayload>): AdminAiPayload | null {
  return result.status === "fulfilled" && isRecord(result.value) ? result.value : null;
}
