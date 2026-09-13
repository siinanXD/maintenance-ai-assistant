export type AdminAiView =
  | "overview"
  | "rag_board"
  | "source_check"
  | "prompt_faq"
  | "effectiveness"
  | "technical";

type AdminAiNavigationItem = {
  readonly description: string;
  readonly href: string;
  readonly label: string;
  readonly view: AdminAiView;
};

type AdminAiViewMeta = {
  readonly description: string;
  readonly href: string;
  readonly label: string;
  readonly lead: string;
  readonly title: string;
  readonly view: AdminAiView;
};

/**
 * Primary Admin-AI navigation focused on operations workflows.
 */
export const ADMIN_AI_PRIMARY_NAVIGATION: readonly AdminAiNavigationItem[] = [
  {
    description: "Status, Alerts, Kosten-Kurzinfo und letzte Aktivität.",
    href: "/admin/ai",
    label: "Betrieb",
    view: "overview"
  },
  {
    description: "Logs, Tracing, Metriken, Retrieval-Diagnose und Jobs.",
    href: "/admin/ai/technical",
    label: "Observability",
    view: "technical"
  },
  {
    description: "Antworten testen, Quellen prüfen, Sicherheit und Feedback.",
    href: "/admin/ai/source-check",
    label: "Antworten",
    view: "source_check"
  },
  {
    description: "Prompt-Versionen, Rollback, FAQ und Feintuning.",
    href: "/admin/ai/prompt-faq",
    label: "Prompts",
    view: "prompt_faq"
  },
  {
    description: "Wissensbasis, Indexstatus, Reindex und Quellenpflege.",
    href: "/admin/ai/rag-board",
    label: "Wissen",
    view: "rag_board"
  }
] as const;

export const ADMIN_AI_VIEW_META: Readonly<Record<AdminAiView, AdminAiViewMeta>> = {
  overview: {
    view: "overview",
    href: "/admin/ai",
    label: "Betrieb",
    title: "KI-Betrieb",
    lead: "Monitoring, Alerts und Einstieg in Logs, Antworten und Prompts.",
    description: "Status, Alerts, Kosten-Kurzinfo und letzte Aktivität."
  },
  technical: {
    view: "technical",
    href: "/admin/ai/technical",
    label: "Observability",
    title: "Observability",
    lead: "Logging, Tracing, Metriken und Retrieval-Diagnose ohne Spieloberfläche.",
    description: "Logs, Tracing, Metriken, Retrieval-Diagnose und Jobs."
  },
  source_check: {
    view: "source_check",
    href: "/admin/ai/source-check",
    label: "Antworten",
    title: "Antworten prüfen",
    lead: "Responses testen, Quellen sichten und Antwortqualität bewerten.",
    description: "Antworten testen, Quellen prüfen, Sicherheit und Feedback."
  },
  prompt_faq: {
    view: "prompt_faq",
    href: "/admin/ai/prompt-faq",
    label: "Prompts",
    title: "Prompts & Tuning",
    lead: "Prompt-Versionen verwalten, FAQ pflegen und Verhalten feinjustieren.",
    description: "Prompt-Versionen, Rollback, FAQ und Feintuning."
  },
  rag_board: {
    view: "rag_board",
    href: "/admin/ai/rag-board",
    label: "Wissen",
    title: "Wissen & Index",
    lead: "Wissensbasis pflegen, Reindex steuern und Quellenstatus prüfen.",
    description: "Wissensbasis, Indexstatus, Reindex und Quellenpflege."
  },
  effectiveness: {
    view: "effectiveness",
    href: "/admin/ai/effectiveness",
    label: "Kosten",
    title: "Kosten & Qualität",
    lead: "Tokenverbrauch, geschätzte Kosten und Qualitätssignale im Detail.",
    description: "Detaillierte Kosten-, Feedback- und Qualitätsauswertung."
  }
};

/**
 * Quick workflow cards shown on the Betrieb overview.
 */
export const ADMIN_AI_WORKFLOW_AREAS: readonly AdminAiViewMeta[] = [
  ADMIN_AI_VIEW_META.technical,
  ADMIN_AI_VIEW_META.source_check,
  ADMIN_AI_VIEW_META.prompt_faq,
  ADMIN_AI_VIEW_META.rag_board
];

/**
 * Return metadata for the active Admin-AI view.
 */
export function adminAiViewMeta(view: AdminAiView): AdminAiViewMeta {
  return ADMIN_AI_VIEW_META[view];
}

/**
 * Resolve the Admin-AI view from the current browser path.
 */
export function resolveAdminAiView(pathname: string): AdminAiView {
  const view = Object.values(ADMIN_AI_VIEW_META).find((item) => item.href === pathname.replace(/\/$/, ""));
  return view?.view ?? "overview";
}
