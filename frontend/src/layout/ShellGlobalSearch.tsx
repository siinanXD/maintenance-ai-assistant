import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import { apiRequest } from "../api/client";
import { hasStoredToken } from "../auth/session";

type ShellGlobalSearchProps = {
  readonly inputId: string;
  readonly isMobile?: boolean;
};

type ShellSearchResult = {
  readonly badge?: string;
  readonly status?: string;
  readonly summary?: string;
  readonly title?: string;
  readonly type?: string;
  readonly ui_url?: string;
  readonly url?: string;
};

type ShellSearchResponse = {
  readonly results?: readonly ShellSearchResult[];
};

type ShellSearchMessage = {
  readonly text: string;
  readonly variant?: "error" | "info";
};

const SEARCH_DEBOUNCE_MS = 220;

/**
 * Return the visible label for one global search result type.
 */
function globalSearchTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    document: "Dokument",
    error: "Störung",
    task: "Aufgabe"
  };
  return labels[type] || "Treffer";
}

/**
 * Return the fallback route used when no direct global search result is selected.
 */
function globalSearchFallbackUrl(query: string): string {
  return `/tasks?search=${encodeURIComponent(query)}`;
}

/**
 * Return a navigation URL for a global search result.
 */
function resultUrl(result: ShellSearchResult, query: string): string {
  return result.ui_url || result.url || globalSearchFallbackUrl(query);
}

/**
 * Convert an unknown API response into a safe global search result list.
 */
function searchResultsFromPayload(payload: ShellSearchResponse): readonly ShellSearchResult[] {
  return Array.isArray(payload.results) ? payload.results : [];
}

/**
 * Group global search results by backend result type.
 */
function groupedSearchResults(
  results: readonly ShellSearchResult[]
): readonly [string, readonly ShellSearchResult[]][] {
  const groups = new Map<string, ShellSearchResult[]>();
  results.forEach((result) => {
    const type = result.type || "result";
    const group = groups.get(type) || [];
    group.push(result);
    groups.set(type, group);
  });
  return Array.from(groups.entries());
}

/**
 * Render the result panel of the global search.
 */
function ShellGlobalSearchResults({
  message,
  query,
  results
}: {
  readonly message: ShellSearchMessage | null;
  readonly query: string;
  readonly results: readonly ShellSearchResult[];
}): ReactNode {
  if (message) {
    return (
      <div className={`global-search-empty${message.variant ? ` is-${message.variant}` : ""}`}>
        {message.text}
      </div>
    );
  }

  return groupedSearchResults(results).map(([type, groupResults]) => (
    <section className="global-search-group" key={type}>
      <h2>{globalSearchTypeLabel(type)}</h2>
      {groupResults.map((result, index) => (
        <a className="global-search-result" href={resultUrl(result, query)} key={`${type}-${index}`}>
          <span className="global-search-result-content">
            <strong>{result.title || "Ohne Titel"}</strong>
            {result.summary ? <small>{result.summary}</small> : null}
          </span>
          {result.badge || result.status ? (
            <span className="global-search-result-badge">{result.badge || result.status}</span>
          ) : null}
        </a>
      ))}
    </section>
  ));
}

/**
 * Render a React-owned global search form for the future app shell.
 */
export function ShellGlobalSearch({ inputId, isMobile = false }: ShellGlobalSearchProps): ReactNode {
  const [activeQuery, setActiveQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [message, setMessage] = useState<ShellSearchMessage | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<readonly ShellSearchResult[]>([]);
  const formRef = useRef<HTMLFormElement | null>(null);
  const className = isMobile ? "global-search is-mobile" : "global-search";

  useEffect(() => {
    const trimmedQuery = query.trim();
    if (trimmedQuery.length < 2) {
      setIsOpen(false);
      setResults([]);
      setMessage(null);
      return undefined;
    }

    const controller = new AbortController();
    const debounceId = window.setTimeout(() => {
      setActiveQuery(trimmedQuery);
      if (!hasStoredToken()) {
        setIsOpen(true);
        setResults([]);
        setMessage({ text: "Bitte zuerst anmelden.", variant: "error" });
        return;
      }

      setIsOpen(true);
      setMessage({ text: "Suche läuft...", variant: "info" });
      apiRequest<ShellSearchResponse>(`/api/v1/search?q=${encodeURIComponent(trimmedQuery)}`, {
        signal: controller.signal
      })
        .then((payload) => {
          const searchResults = searchResultsFromPayload(payload);
          setResults(searchResults);
          setMessage(
            searchResults.length
              ? null
              : { text: "Keine Treffer. Enter öffnet die Aufgabensuche.", variant: "info" }
          );
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          console.warn(error);
          setResults([]);
          setMessage({ text: "Suche konnte nicht geladen werden.", variant: "error" });
        });
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      controller.abort();
      window.clearTimeout(debounceId);
    };
  }, [query]);

  useEffect(() => {
    /**
     * Close the search panel after clicks outside this form.
     */
    function handleDocumentClick(event: MouseEvent): void {
      if (!formRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    document.addEventListener("click", handleDocumentClick);
    return () => document.removeEventListener("click", handleDocumentClick);
  }, []);

  /**
   * Submit the current global search and navigate to the best target.
   */
  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const trimmedQuery = query.trim();
    if (!trimmedQuery) return;
    const firstResult = results[0];
    window.location.href = firstResult ? resultUrl(firstResult, trimmedQuery) : globalSearchFallbackUrl(trimmedQuery);
  }

  return (
    <form className={className} role="search" autoComplete="off" onSubmit={handleSubmit} ref={formRef}>
      <label className="sr-only" htmlFor={inputId}>Globale Suche</label>
      <input
        id={inputId}
        type="search"
        placeholder="Aufgaben, Fehler, Dokumente suchen"
        aria-label="Globale Suche"
        value={query}
        onChange={(event) => setQuery(event.currentTarget.value)}
        onFocus={() => {
          if (query.trim().length >= 2) setIsOpen(true);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") setIsOpen(false);
        }}
      />
      <div className="global-search-panel" hidden={!isOpen}>
        <div className="global-search-results">
          <ShellGlobalSearchResults message={message} query={activeQuery || query} results={results} />
        </div>
      </div>
    </form>
  );
}
