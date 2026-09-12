import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import { apiRequest } from "../api/client";
import { hasStoredToken } from "../auth/session";

type ChatMessageRole = "assistant" | "user";

type ShellChatSource = {
  readonly count?: number;
  readonly module?: string;
  readonly source_type?: string;
  readonly title?: string;
  readonly type?: string;
  readonly url?: string;
};

type ShellChatAnswerQuality = {
  readonly no_answer?: boolean;
  readonly source_count?: number;
  readonly status?: string;
  readonly uncertainty?: string;
};

type ShellChatDiagnostics = {
  readonly answer_category?: string;
  readonly answer_origin?: string;
  readonly evidence_visible?: boolean;
  readonly fallback_used?: boolean;
  readonly retrieval_used?: boolean;
  readonly source_label?: string;
  readonly source_count?: number;
  readonly status?: string;
};

type ShellChatPendingAction = {
  readonly label?: string;
  readonly token: string;
  readonly tool?: string;
};

type ShellChatMessage = {
  readonly id: string;
  readonly isLoading?: boolean;
  readonly meta?: ShellChatAnswerMeta;
  readonly pendingAction?: ShellChatPendingAction;
  readonly role: ChatMessageRole;
  readonly text: string;
};

type ShellChatResponse = {
  readonly answer?: string;
  readonly answer_category?: string;
  readonly answer_quality?: ShellChatAnswerQuality;
  readonly data?: ShellChatResponse;
  readonly diagnostics?: ShellChatDiagnostics;
  readonly evidence_visible?: boolean;
  readonly pending_action?: ShellChatPendingAction;
  readonly retrieval_used?: boolean;
  readonly source_label?: string;
  readonly sources?: readonly ShellChatSource[];
  readonly success?: boolean;
  readonly type?: string;
};

type ShellChatAnswerMeta = {
  readonly answerType: string;
  readonly appDataBadge: boolean;
  readonly evidenceLabel: string;
  readonly sourceCount: number;
  readonly sourceLabel: string;
  readonly sourceItems: readonly string[];
  readonly structured: boolean;
  readonly uncertaintyLabel: string;
  readonly zeroResult: boolean;
};

const CHAT_OPEN_KEY = "maintenance_chat_open";
const CHAT_SESSION_KEY = "maintenance_ai_chat_session_id";
const INITIAL_ASSISTANT_MESSAGE = "Frag mich nach kritischen Störungen, niedriger Sicherheit, veralteten Dokumenten oder heutigen Entscheidungen.";

/**
 * Return a compact random identifier for one browser chat session.
 */
function buildChatSessionId(): string {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }
  return `chat-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Return the current short-term chat session id.
 */
function chatSessionId(): string {
  const existing = window.sessionStorage.getItem(CHAT_SESSION_KEY);
  if (existing) return existing;
  const nextSessionId = buildChatSessionId();
  window.sessionStorage.setItem(CHAT_SESSION_KEY, nextSessionId);
  return nextSessionId;
}

/**
 * Start a new short-term React chat session.
 */
function resetChatSession(): string {
  const nextSessionId = buildChatSessionId();
  window.sessionStorage.setItem(CHAT_SESSION_KEY, nextSessionId);
  return nextSessionId;
}

/**
 * Return a stable local chat message id.
 */
function chatMessageId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * Normalize wrapped and direct backend chat payloads.
 */
function responseData(payload: ShellChatResponse): ShellChatResponse {
  return payload.answer
    ? payload
    : payload.success === true && payload.data
      ? payload.data
      : payload;
}

/**
 * Normalize the backend chat response into the answer text shown in the shell widget.
 */
function answerFromPayload(payload: ShellChatResponse): string {
  const data = responseData(payload);
  const diagnostics = data.diagnostics || {};
  let answer = data.answer || "Ich habe keine Antwort erhalten.";

  if (diagnostics.status === "api_key_missing") {
    answer += "\n- Hinweis: Lokale Ausweichantwort, AI API-Key fehlt";
  }
  if (diagnostics.status === "openai_error") {
    answer += "\n- Hinweis: Lokale Ausweichantwort, OpenAI nicht erreichbar";
  }
  if (diagnostics.fallback_used) {
    answer += "\n- Quelle: Lokale Ausweichantwort";
  }

  return answer;
}

/**
 * Return compact display metadata for one chat answer.
 */
function metaFromPayload(payload: ShellChatResponse): ShellChatAnswerMeta {
  const data = responseData(payload);
  const diagnostics = data.diagnostics || {};
  const answerQuality = data.answer_quality || {};
  const sources = data.sources || [];
  const sourceItems = sources.map(sourceItemLabel).filter(Boolean).slice(0, 3);
  const sourceCount = sourceCountFromPayload(data, sourceItems.length);
  const answerCategory = String(
    data.answer_category || diagnostics.answer_category || ""
  ).trim();
  const answerType = answerTypeLabel(data.type);
  const structured = isStructuredAnswer(data.type, answerCategory);
  const appDataBadge = structured || answerCategory === "structured_data";
  const sourceLabel = sourceLabelFromPayload(data, sourceItems, answerType);
  const zeroResult = isZeroResult(data.answer || "", data, sourceCount);

  return {
    answerType: appDataBadge ? "App-Daten" : answerType,
    appDataBadge,
    evidenceLabel: evidenceLabel(data.evidence_visible, diagnostics.evidence_visible),
    sourceCount,
    sourceLabel,
    sourceItems,
    structured,
    uncertaintyLabel: uncertaintyLabel(answerQuality.uncertainty, answerQuality.status),
    zeroResult
  };
}

/**
 * Return the pending agent action carried by a chat response, if any.
 */
function pendingActionFromPayload(payload: ShellChatResponse): ShellChatPendingAction | undefined {
  const data = responseData(payload);
  const pending = data.pending_action;
  if (!pending || typeof pending.token !== "string" || !pending.token) return undefined;
  return { label: pending.label, token: pending.token, tool: pending.tool };
}

/**
 * Return a human-readable answer type label.
 */
function answerTypeLabel(typeValue: unknown): string {
  const key = String(typeValue || "").trim();
  const labels: Record<string, string> = {
    agent: "Agent",
    agent_action: "Agent-Aktion",
    daily_briefing: "Daily Briefing",
    document_outdated: "Dokumente",
    document_recent: "Dokumente",
    document_this_week: "Dokumente",
    error_help: "Fehlerhilfe",
    general_chat: "AI-Antwort",
    structured_scope: "App-Daten",
    tasks_status: "Task-Status",
    tasks_today: "Heutige Tasks"
  };
  return labels[key] || (key ? "App-Daten" : "Antwort");
}

/**
 * Return whether a response type represents structured app data.
 */
function isStructuredAnswer(typeValue: unknown, answerCategory = ""): boolean {
  if (answerCategory === "structured_data") return true;
  const key = String(typeValue || "");
  return (
    key === "daily_briefing"
    || key === "structured_scope"
    || key.startsWith("document_")
    || key.startsWith("employee_")
    || key.startsWith("inventory_")
    || key.startsWith("machine_")
    || key.startsWith("shiftplan_")
    || key.startsWith("tasks_")
    || key.startsWith("vacation_")
    || key.endsWith("_count")
  );
}

/**
 * Return the best available source count from response metadata.
 */
function sourceCountFromPayload(data: ShellChatResponse, visibleSourceCount: number): number {
  const diagnosticsCount = numericValue(data.diagnostics?.source_count);
  const qualityCount = numericValue(data.answer_quality?.source_count);
  return Math.max(visibleSourceCount, diagnosticsCount, qualityCount);
}

/**
 * Return a display label for the source backing the answer.
 */
function sourceLabelFromPayload(
  data: ShellChatResponse,
  sourceItems: readonly string[],
  answerType: string
): string {
  const moduleLabel = firstSourceModuleLabel(data.sources || []);
  if (moduleLabel) return `Quelle: ${moduleLabel}`;
  const explicitSourceLabel = String(data.source_label || data.diagnostics?.source_label || "").trim();
  if (explicitSourceLabel) return `Quelle: ${explicitSourceLabel}`;
  const answerSource = sourceLabelFromAnswer(data.answer || "");
  if (answerSource) return `Quelle: ${normalizedSourceLabel(answerSource)}`;
  if (answerType === "Daily Briefing") return "Quelle: Daily Briefing";
  if (answerType !== "Antwort") return `Quelle: ${answerType}`;
  return sourceItems.length ? "Quelle: freigegebene App-Daten" : "Quelle: geprüft";
}

/**
 * Return one source module label from visible source cards.
 */
function firstSourceModuleLabel(sources: readonly ShellChatSource[]): string {
  const first = sources.find((source) => source.module || source.type || source.source_type);
  if (!first) return "";
  const key = String(first.module || first.type || first.source_type || "");
  const labels: Record<string, string> = {
    daily_briefing: "Daily Briefing",
    documents: "Dokumente",
    errors: "Störungen",
    inventory: "Lager",
    knowledge: "Wissensdatenbank",
    machines: "Maschinen",
    shiftplans: "Schichtplanung",
    tasks: "Tasks"
  };
  return labels[key] || first.title || key;
}

/**
 * Return a user-facing source label for known structured source phrases.
 */
function normalizedSourceLabel(sourceLabel: string): string {
  const normalized = sourceLabel.toLowerCase();
  if (normalized.includes("daily-briefing") || normalized.includes("daily briefing")) {
    return "Daily Briefing";
  }
  if (normalized.includes("task")) return "Tasks";
  if (normalized.includes("dokument")) return "Dokumente";
  if (normalized.includes("fehler") || normalized.includes("stoerung")) return "Störungen";
  if (normalized.includes("lager") || normalized.includes("material")) return "Lager";
  if (normalized.includes("mitarbeiter")) return "Mitarbeiter";
  if (normalized.includes("maschine")) return "Maschinen";
  return sourceLabel;
}

/**
 * Return the source label embedded in structured answer text.
 */
function sourceLabelFromAnswer(answer: string): string {
  const lines = answer.split("\n");
  const sourceLine = lines.find((line) => line.includes("Quelle"));
  const headingLine = lines.find((line) => line.startsWith("## "));
  if (!sourceLine) return headingLine ? normalizedSourceLabel(headingLine.replace(/^##\s+/, "")) : "";
  const sourceLabel = sourceLine
    .replace(/^[-\s]*/, "")
    .replace(/\*\*/g, "")
    .replace(/^Quelle:\s*/i, "")
    .trim();
  if (sourceLabel.toLowerCase() === "strukturierte daten" && headingLine) {
    return normalizedSourceLabel(headingLine.replace(/^##\s+/, ""));
  }
  return sourceLabel;
}

/**
 * Return a compact source item label for visible source cards.
 */
function sourceItemLabel(source: ShellChatSource): string {
  const title = String(source.title || source.module || source.type || "").trim();
  const count = numericValue(source.count);
  if (title && source.count !== undefined) return `${title}: ${count}`;
  return title;
}

/**
 * Return whether the answer is a checked zero-result response.
 */
function isZeroResult(answer: string, data: ShellChatResponse, sourceCount: number): boolean {
  const lowerAnswer = answer.toLowerCase();
  if (sourceCount > 0 && (lowerAnswer.includes("keine ") || lowerAnswer.includes("anzahl:** 0"))) {
    return true;
  }
  return data.answer_quality?.no_answer === false && lowerAnswer.includes("0");
}

/**
 * Return an evidence visibility label without exposing hidden details.
 */
function evidenceLabel(evidenceVisible: unknown, diagnosticEvidenceVisible: unknown): string {
  if (evidenceVisible === false || diagnosticEvidenceVisible === false) {
    return "Details ausgeblendet";
  }
  return "Details sichtbar";
}

/**
 * Return a localized uncertainty label.
 */
function uncertaintyLabel(uncertainty: unknown, status: unknown): string {
  const value = String(uncertainty || "").trim();
  const labels: Record<string, string> = {
    high: "Unsicherheit: hoch",
    low: "Unsicherheit: niedrig",
    medium: "Unsicherheit: mittel"
  };
  if (labels[value]) return labels[value];
  if (String(status || "") === "grounded") return "Unsicherheit: niedrig";
  return "Unsicherheit: geprüft";
}

/**
 * Return a numeric value or zero.
 */
function numericValue(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * Render simple Markdown-like answer text into readable blocks.
 */
function renderAnswerText(text: string): ReactNode {
  return text.split("\n").map((line, index) => {
    const key = `${line}-${index}`;
    if (line.startsWith("## ")) {
      return <strong className="chat-answer-heading" key={key}>{line.replace(/^##\s+/, "")}</strong>;
    }
    if (line.startsWith("- ")) {
      return <span className="chat-answer-line" key={key}>{cleanAnswerLine(line)}</span>;
    }
    if (!line.trim()) {
      return <span className="chat-answer-gap" key={key} aria-hidden="true" />;
    }
    return <span className="chat-answer-line" key={key}>{cleanAnswerLine(line)}</span>;
  });
}

/**
 * Return answer text without lightweight Markdown decoration.
 */
function cleanAnswerLine(line: string): string {
  return line.replace(/^-\s*/, "").replace(/\*\*/g, "");
}

/**
 * Render one React-owned chat message bubble.
 */
function ShellChatMessageBubble({
  message,
  onConfirm
}: {
  readonly message: ShellChatMessage;
  readonly onConfirm?: (message: ShellChatMessage) => void;
}): ReactNode {
  const className = [
    "chat-message",
    message.role === "assistant" ? "is-assistant" : "is-user",
    message.meta?.structured ? "chat-answer-card" : "",
    message.isLoading ? "is-loading" : ""
  ].filter(Boolean).join(" ");

  if (message.role !== "assistant" || !message.meta) {
    return <div className={className}>{message.text}</div>;
  }

  return (
    <article className={className}>
      <div className="chat-answer-meta" aria-label="Antwort-Metadaten">
        <span>{message.meta.answerType}</span>
        {message.meta.appDataBadge ? (
          <span className="chat-answer-badge is-positive">App-Daten</span>
        ) : null}
        <span>{message.meta.sourceLabel}</span>
        <span>{sourceStatusLabel(message.meta)}</span>
      </div>
      <div className="chat-answer-body">{renderAnswerText(message.text)}</div>
      <div className="chat-answer-footnote">
        <span>{message.meta.uncertaintyLabel}</span>
        <span>{message.meta.evidenceLabel}</span>
      </div>
      {message.meta.sourceItems.length ? (
        <div className="chat-source-chips" aria-label="Sichtbare Quellen">
          {message.meta.sourceItems.map((sourceLabel) => (
            <span key={sourceLabel}>{sourceLabel}</span>
          ))}
        </div>
      ) : null}
      {message.pendingAction && onConfirm ? (
        <div className="chat-pending-action" data-chat-pending-action>
          <span>Aktion wartet auf Bestätigung: {message.pendingAction.label || message.pendingAction.tool}</span>
          <button className="btn btn-sm btn-primary" type="button" onClick={() => onConfirm(message)}>
            Aktion bestätigen
          </button>
        </div>
      ) : null}
    </article>
  );
}

/**
 * Return the source status shown in the compact answer metadata row.
 */
function sourceStatusLabel(meta: ShellChatAnswerMeta): string {
  if (meta.sourceLabel === "Quelle: Modellwissen") return "Modellwissen";
  if (meta.zeroResult) return "0 Treffer geprüft";
  if (meta.sourceCount > 0) return `${meta.sourceCount} Quellen`;
  return "App-Daten geprüft";
}

/**
 * Render the global AI chat widget hooks and behavior for the future React shell.
 */
export function ShellChatWidget(): ReactNode {
  const [inputValue, setInputValue] = useState("");
  const [isOpen, setIsOpen] = useState(() => window.localStorage.getItem(CHAT_OPEN_KEY) === "true");
  const [isSending, setIsSending] = useState(false);
  const [messages, setMessages] = useState<readonly ShellChatMessage[]>([
    {
      id: "assistant-initial",
      role: "assistant",
      text: INITIAL_ASSISTANT_MESSAGE
    }
  ]);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const widgetClassName = isOpen ? "chat-widget is-open" : "chat-widget";
  const loadingText = "Ich prüfe die freigegebenen Daten und formuliere eine sichere Antwort...";

  useEffect(() => {
    window.localStorage.setItem(CHAT_OPEN_KEY, String(isOpen));
    if (isOpen) {
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [isOpen]);

  /**
   * Reset the visible chat and start a new short-term session.
   */
  function clearChat(): void {
    resetChatSession();
    setMessages([
      {
        id: "assistant-initial",
        role: "assistant",
        text: INITIAL_ASSISTANT_MESSAGE
      }
    ]);
    setInputValue("");
  }

  /**
   * Submit a React-owned chat request to the existing AI endpoint.
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const message = inputValue.trim();
    if (!message || isSending) return;

    const loadingId = chatMessageId("assistant-loading");
    setInputValue("");
    setIsSending(true);
    setMessages((currentMessages) => [
      ...currentMessages,
      { id: chatMessageId("user"), role: "user", text: message },
      { id: loadingId, isLoading: true, role: "assistant", text: loadingText }
    ]);

    try {
      if (!hasStoredToken()) {
        throw new Error("Bitte zuerst einloggen. Danach kann ich die KI-Funktionen nutzen.");
      }

      const payload = await apiRequest<ShellChatResponse>("/api/v1/ai/chat", {
        body: {
          message,
          response_mode: "answer_only",
          session_id: chatSessionId()
        },
        method: "POST"
      });
      const answer = answerFromPayload(payload);
      const meta = metaFromPayload(payload);
      const pendingAction = pendingActionFromPayload(payload);
      setMessages((currentMessages) => currentMessages.map((item) => (
        item.id === loadingId
          ? { id: loadingId, meta, pendingAction, role: "assistant", text: answer }
          : item
      )));
    } catch (error) {
      const fallbackMessage = error instanceof Error
        ? error.message
        : "Keine Verbindung zur API. Bitte prüfe, ob der Server läuft.";
      setMessages((currentMessages) => currentMessages.map((item) => (
        item.id === loadingId ? { id: loadingId, role: "assistant", text: fallbackMessage } : item
      )));
    } finally {
      setIsSending(false);
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  }

  /**
   * Confirm a pending agent write action and show the outcome in the chat.
   */
  async function confirmAction(message: ShellChatMessage): Promise<void> {
    const pending = message.pendingAction;
    if (!pending || isSending) return;
    setIsSending(true);
    setMessages((currentMessages) => currentMessages.map((item) => (
      item.id === message.id ? { ...item, pendingAction: undefined } : item
    )));
    try {
      const payload = await apiRequest<ShellChatResponse>("/api/v1/ai/agent/confirm", {
        body: { session_id: chatSessionId(), token: pending.token },
        method: "POST"
      });
      setMessages((currentMessages) => [
        ...currentMessages,
        {
          id: chatMessageId("assistant-action"),
          meta: metaFromPayload(payload),
          role: "assistant",
          text: answerFromPayload(payload)
        }
      ]);
    } catch (error) {
      const fallbackMessage = error instanceof Error
        ? error.message
        : "Die Aktion konnte nicht ausgeführt werden.";
      setMessages((currentMessages) => [
        ...currentMessages,
        { id: chatMessageId("assistant-action-error"), role: "assistant", text: fallbackMessage }
      ]);
    } finally {
      setIsSending(false);
    }
  }

  return (
    <section className={widgetClassName} aria-label="AI Chat">
      <button
        className="chat-toggle"
        type="button"
        aria-expanded={isOpen}
        aria-controls="chat-panel"
        onClick={() => setIsOpen((currentValue) => !currentValue)}
      >
        <span aria-hidden="true">AI</span>
      </button>
      <div
        className="chat-panel"
        id="chat-panel"
        role="dialog"
        aria-modal={isOpen}
        aria-labelledby="chat-panel-title"
        aria-hidden={!isOpen}
        tabIndex={-1}
      >
        <div className="chat-panel-header">
          <div>
            <p className="chat-panel-kicker">Maintenance AI</p>
            <h2 className="chat-panel-title" id="chat-panel-title">Lage klären</h2>
          </div>
          <button className="chat-clear" type="button" aria-label="Chat leeren" title="Chat leeren" onClick={clearChat}>
            Neu
          </button>
          <button className="chat-close" type="button" aria-label="Chat schließen" onClick={() => setIsOpen(false)}>
            &times;
          </button>
        </div>
        <div className="chat-panel-body" data-chat-messages role="log" aria-live="polite" aria-relevant="additions text">
          {messages.map((message) => (
            <ShellChatMessageBubble key={message.id} message={message} onConfirm={confirmAction} />
          ))}
        </div>
        <details className="help-disclosure chat-guidance">
          <summary>Worauf basiert die Antwort?</summary>
          <p>Der Assistant nutzt freigegebene App-Daten und, wenn aktiv, passende Dokumentquellen. Quellen, Konfidenz und Unsicherheit werden in der Antwortkarte angezeigt.</p>
        </details>
        <details className="chat-history-panel" data-chat-history-panel hidden>
          <summary className="chat-history-summary" data-chat-history-summary>
            Chat-Historie
            <span data-chat-history-count>0</span>
          </summary>
          <label className="sr-only" htmlFor="chat-history-search-react">Chat-Historie durchsuchen</label>
          <input className="input input-bordered w-full" id="chat-history-search-react" data-chat-history-search autoComplete="off" placeholder="Historie durchsuchen" />
          <div className="chat-history-list" data-chat-history-list />
        </details>
        <div className="chat-suggestions" data-chat-suggestions hidden />
        <form className="chat-panel-form" data-chat-form aria-describedby="chat-input-help-react" aria-busy={isSending} onSubmit={handleSubmit}>
          <label className="sr-only" htmlFor="chat-message-input-react">Nachricht an den AI Assistant</label>
          <input
            className="input input-bordered w-full"
            id="chat-message-input-react"
            name="message"
            autoComplete="off"
            placeholder="z. B. Presse 3 verliert Hydraulik"
            aria-describedby="chat-input-help-react"
            disabled={isSending}
            onChange={(event) => setInputValue(event.currentTarget.value)}
            ref={inputRef}
            value={inputValue}
          />
          <span className="sr-only" id="chat-input-help-react">Der Assistant nutzt nur freigegebene Daten; schreibende Aktionen brauchen deine Bestätigung.</span>
          <button className="btn btn-primary" type="submit" disabled={isSending}>
            {isSending ? "Analysiere..." : "Senden"}
          </button>
        </form>
      </div>
    </section>
  );
}
