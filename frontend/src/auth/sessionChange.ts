import { readStoredSession } from "./session";

const AUTH_EVENTS = ["maintenance-auth-ready", "maintenance-auth-changed"] as const;

/**
 * Call onChange only when the stored session token actually changes.
 *
 * auth.js dispatches "maintenance-auth-ready" on every page load, also when the
 * session is exactly the one the page already used for its first request. Pages
 * that reloaded all data on that event fetched everything twice per visit.
 */
export function subscribeToSessionChange(onChange: () => void): () => void {
  let lastToken = readStoredSession().token;

  /**
   * Compare the current token with the last one this subscription saw.
   */
  function handleAuthEvent(): void {
    const token = readStoredSession().token;
    if (token === lastToken) return;
    lastToken = token;
    onChange();
  }

  AUTH_EVENTS.forEach((eventName) => window.addEventListener(eventName, handleAuthEvent));
  return () => {
    AUTH_EVENTS.forEach((eventName) => window.removeEventListener(eventName, handleAuthEvent));
  };
}
