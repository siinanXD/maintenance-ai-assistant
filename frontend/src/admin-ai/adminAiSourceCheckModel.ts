import { safeErrorMessage } from "../utils/errors";
import { type AdminAiPayload } from "./adminAiApi";
import { moneyText, numberText } from "./adminAiFormat";

type AdminAiSourceTestMode = "dry" | "live";

export type AdminAiSourceTestSource = {
  readonly meta: string;
  readonly title: string;
};

type AdminAiSourceTestKpis = {
  readonly confidence: string;
  readonly cost: string;
  readonly latency: string;
  readonly sources: string;
};

type AdminAiSourceTestRecord = {
  readonly mode: AdminAiSourceTestMode;
  readonly question: string;
  readonly result: AdminAiPayload;
};

export type AdminAiSourceCheckState = {
  readonly actionsVisible: boolean;
  readonly answerText: string;
  readonly errorMessage: string;
  readonly isRunning: boolean;
  readonly isSaving: boolean;
  readonly kpis: AdminAiSourceTestKpis;
  readonly latestTest: AdminAiSourceTestRecord | null;
  readonly promptMeta: string;
  readonly promptPreview: string;
  readonly reportedSourceCount: number;
  readonly sources: readonly AdminAiSourceTestSource[];
  readonly stateClassName: string;
  readonly stateLabel: string;
  readonly statusMessage: string;
  readonly testMeta: string;
};

const EMPTY_SOURCE_KPIS: AdminAiSourceTestKpis = {
  confidence: "-",
  cost: "$0",
  latency: "0 ms",
  sources: "0"
};

export const EMPTY_ADMIN_AI_SOURCE_CHECK_STATE: AdminAiSourceCheckState = {
  actionsVisible: false,
  answerText: "Wähle Dry-run für Prompt/Kosten-Nähe oder Live-Test für echte Antwort mit Quellen.",
  errorMessage: "",
  isRunning: false,
  isSaving: false,
  kpis: EMPTY_SOURCE_KPIS,
  latestTest: null,
  promptMeta: "Noch kein Dry-run",
  promptPreview: "Wähle Workflow und Frage.",
  reportedSourceCount: 0,
  sources: [],
  stateClassName: "status-pill is-muted",
  stateLabel: "Bereit",
  statusMessage: "",
  testMeta: "Noch keine Testfrage ausgeführt"
};

/**
 * Return true when a value can be read as an object payload.
 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Return a string field from an unknown API payload.
 */
function stringField(payload: AdminAiPayload, key: string): string {
  const value = payload[key];
  return typeof value === "string" ? value : "";
}

/**
 * Return an object field from an unknown API payload.
 */
function objectField(payload: AdminAiPayload, key: string): Record<string, unknown> {
  const value = payload[key];
  return isRecord(value) ? value : {};
}

/**
 * Normalize the visible Source Check form into a plain payload.
 */
export function sourceCheckFormPayload(form: HTMLFormElement): Record<string, unknown> {
  return Object.fromEntries(new FormData(form).entries());
}

/**
 * Build the backend payload for a Source Check prompt dry-run.
 */
export function sourceCheckDryRunPayload(
  payload: Record<string, unknown>
): Record<string, unknown> {
  const workflow = String(payload.workflow || "chat");
  const promptMode = workflow === "general_chat" || workflow === "chat" ? "text" : "json";

  return {
    ...payload,
    mode: promptMode
  };
}

/**
 * Build the live chat payload for Source Check.
 */
export function sourceCheckChatPayload(payload: Record<string, unknown>): Record<string, unknown> {
  const question = String(payload.question || "").trim();
  const context = String(payload.context || "").trim();

  return {
    message: context ? `${question}\n\nKontext: ${context}` : question
  };
}

/**
 * Return the question text used for feedback and FAQ creation.
 */
export function sourceCheckQuestion(payload: Record<string, unknown>): string {
  return String(payload.question || "").trim();
}

/**
 * Return a readable answer from an AI Source Check result.
 */
function sourceTestAnswerText(result: AdminAiPayload): string {
  return (
    stringField(result, "answer")
    || stringField(result, "response")
    || stringField(result, "message")
    || "Keine Antwort im Ergebnis."
  );
}

/**
 * Return diagnostics from an AI Source Check result.
 */
function sourceTestDiagnostics(result: AdminAiPayload): Record<string, unknown> {
  return objectField(result, "diagnostics");
}

/**
 * Return the estimated cost from an AI Source Check result.
 */
function sourceTestCost(result: AdminAiPayload): unknown {
  const diagnostics = sourceTestDiagnostics(result);
  return diagnostics.estimated_cost_usd || diagnostics.cost_usd || diagnostics.cost || 0;
}

/**
 * Return the source array from an AI Source Check result.
 */
function sourceTestSourcePayloads(result: AdminAiPayload): readonly Record<string, unknown>[] {
  const sources = result.sources;
  return Array.isArray(sources) ? sources.filter(isRecord) : [];
}

/**
 * Return the best available source count, including metadata-only source references.
 */
function sourceTestReportedSourceCount(result: AdminAiPayload): number {
  const visibleSourceCount = sourceTestSourcePayloads(result).length;
  const diagnostics = sourceTestDiagnostics(result);
  const answerQuality = objectField(result, "answer_quality");
  const candidates = [
    diagnostics.source_count,
    diagnostics.final_visible_sources,
    answerQuality.source_count,
    result.source_count,
    visibleSourceCount
  ];
  const numericCounts = candidates
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value) && value >= 0);

  return Math.max(visibleSourceCount, ...numericCounts);
}

/**
 * Build Source Check KPI values from one result.
 */
function sourceTestKpis(result: AdminAiPayload): AdminAiSourceTestKpis {
  const diagnostics = sourceTestDiagnostics(result);
  const sourceCount = sourceTestReportedSourceCount(result);
  const confidenceScore = diagnostics.confidence_score;
  const confidenceLevel = diagnostics.confidence_level;
  const latency = diagnostics.latency_ms || diagnostics.duration_ms || 0;

  return {
    confidence:
      typeof confidenceLevel === "string"
        ? confidenceLevel
        : confidenceScore != null
          ? `${String(confidenceScore)}/100`
          : "-",
    cost: moneyText(sourceTestCost(result)),
    latency: `${numberText(latency)} ms`,
    sources: String(sourceCount)
  };
}

/**
 * Normalize Source Check sources for rendering.
 */
function sourceTestSources(result: AdminAiPayload): readonly AdminAiSourceTestSource[] {
  return sourceTestSourcePayloads(result)
    .slice(0, 8)
    .map((source, index) => {
      const title = source.title || source.name;
      const score = source.score;
      const meta = [
        source.type || source.source_type || "knowledge",
        score != null ? `Score ${String(score)}` : "",
        source.reason || source.module || ""
      ]
        .filter(Boolean)
        .join(" - ");

      return {
        meta,
        title: typeof title === "string" && title.trim() ? title : `Quelle ${index + 1}`
      };
    });
}

/**
 * Convert a prompt dry-run payload into a Source Check result state.
 */
export function sourceCheckDryRunState(
  dryRunPayload: AdminAiPayload,
  question: string
): AdminAiSourceCheckState {
  const promptPreview = JSON.stringify(dryRunPayload.messages || [], null, 2);
  const dryResult: AdminAiPayload = {
    answer: promptPreview,
    diagnostics: { estimated_cost_usd: 0, latency_ms: 0 },
    sources: []
  };

  return {
    ...EMPTY_ADMIN_AI_SOURCE_CHECK_STATE,
    answerText: promptPreview,
    kpis: sourceTestKpis(dryResult),
    latestTest: { mode: "dry", question, result: dryResult },
    promptMeta: `Prompt-Zeichen: ${numberText(dryRunPayload.estimated_prompt_characters || 0)}`,
    promptPreview,
    reportedSourceCount: 0,
    stateClassName: "status-pill is-muted",
    stateLabel: "Dry-run",
    testMeta: "Dry-run ausgeführt. Kein Modellaufruf und keine Kosten."
  };
}

/**
 * Convert a live chat payload into a Source Check result state.
 */
export function sourceCheckLiveState(
  result: AdminAiPayload,
  question: string
): AdminAiSourceCheckState {
  return {
    ...EMPTY_ADMIN_AI_SOURCE_CHECK_STATE,
    actionsVisible: true,
    answerText: sourceTestAnswerText(result),
    kpis: sourceTestKpis(result),
    latestTest: { mode: "live", question, result },
    reportedSourceCount: sourceTestReportedSourceCount(result),
    sources: sourceTestSources(result),
    stateClassName: "status-pill is-active",
    stateLabel: "Live",
    testMeta:
      "Live-Test ausgeführt. Bewerte die Antwort, damit Retrieval-Qualität messbar wird."
  };
}

/**
 * Return a Source Check state with a safe user-facing error message.
 */
export function failedSourceCheckState(error: unknown): AdminAiSourceCheckState {
  return {
    ...EMPTY_ADMIN_AI_SOURCE_CHECK_STATE,
    errorMessage: safeErrorMessage(error, "Quellenprüfung konnte nicht geladen werden.")
  };
}

/**
 * Build the feedback payload for a live Source Check result.
 */
export function sourceCheckFeedbackPayload(
  latestTest: AdminAiSourceTestRecord,
  rating: string,
  comment: string
): Record<string, unknown> {
  const diagnostics = sourceTestDiagnostics(latestTest.result);

  return {
    audit_event_id: diagnostics.audit_event_id,
    chat_message_id: latestTest.result.chat_message_id,
    comment,
    prompt: latestTest.question,
    rating,
    response: sourceTestAnswerText(latestTest.result),
    response_type: latestTest.result.response_type || "assistant",
    sources: latestTest.result.sources || []
  };
}

/**
 * Build the FAQ draft payload for a live Source Check result.
 */
export function sourceCheckFaqPayload(
  latestTest: AdminAiSourceTestRecord
): Record<string, unknown> {
  return {
    answer: sourceTestAnswerText(latestTest.result),
    question: latestTest.question,
    source: "chat",
    source_ref_id: latestTest.result.chat_message_id,
    status: "draft"
  };
}
