import { type AdminAiPayload } from "./adminAiApi";

export type AdminAiSourceTestMode = "dry" | "live";

export type AdminAiSourceTestSource = {
  readonly meta: string;
  readonly title: string;
};

export type AdminAiSourceTestKpis = {
  readonly confidence: string;
  readonly cost: string;
  readonly latency: string;
  readonly sources: string;
};

export type AdminAiSourceTestRecord = {
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
