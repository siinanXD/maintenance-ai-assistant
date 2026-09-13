import { useEffect, useState, type ReactNode } from "react";

import { authRuntime } from "../app/runtimeBridge";
import { readStoredSession } from "../auth/session";
import { LoginForm } from "./components/LoginForm";
import type { LoginData } from "./loginTypes";

const LOGIN_CAPABILITIES = [
  ["Störungen", "Mit Foto melden, mit dem Fehlerkatalog abgleichen, Auftrag anlegen"],
  ["Aufgaben", "Ersatzteile buchen, Bestand und Bestellvorschlag im Blick"],
  ["Prüfungen", "Prüfpflichten mit Frist, Nachweis und Folgeauftrag"],
  ["Assistent", "Antworten aus App-Daten und Handbüchern mit Quelle"]
] as const;

/**
 * Render the logged-in panel shown when a session already exists.
 */
function LoggedInPanel(): ReactNode {
  return (
    <article className="login-card">
      <p className="page-kicker">Sitzung aktiv</p>
      <h2 className="login-card-title">Du bist angemeldet</h2>
      <p className="login-card-meta">Weiter zum Cockpit oder abmelden, um das Konto zu wechseln.</p>
      <div className="login-actions">
        <a className="btn btn-primary" href="/">Zum Cockpit</a>
        <button className="btn btn-ghost" type="button" onClick={() => void authRuntime()?.logout?.()}>Abmelden</button>
      </div>
    </article>
  );
}

/**
 * Render the product panel beside the login form.
 */
function LoginBrandPanel(): ReactNode {
  return (
    <section className="login-brand" aria-label="Maintenance Assistant">
      <div className="login-brand-mark">
        <span className="sidebar-brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" role="img">
            <path d="M19.4 13.5c.1-.5.1-1 .1-1.5s0-1-.1-1.5l2-1.5-2-3.4-2.4 1a8.2 8.2 0 0 0-2.6-1.5L14 2.5h-4l-.4 2.6A8.2 8.2 0 0 0 7 6.6l-2.4-1-2 3.4 2 1.5c-.1.5-.1 1-.1 1.5s0 1 .1 1.5l-2 1.5 2 3.4 2.4-1a8.2 8.2 0 0 0 2.6 1.5l.4 2.6h4l.4-2.6a8.2 8.2 0 0 0 2.6-1.5l2.4 1 2-3.4-2-1.5ZM12 15.5A3.5 3.5 0 1 1 12 8a3.5 3.5 0 0 1 0 7.5Z" />
          </svg>
        </span>
        <span>Maintenance Assistant</span>
      </div>
      <h1 className="login-brand-title">Instandhaltung, Schicht und Wissen an einem Ort.</h1>
      <dl className="login-capabilities">
        {LOGIN_CAPABILITIES.map(([term, description]) => (
          <div key={term}>
            <dt>{term}</dt>
            <dd>{description}</dd>
          </div>
        ))}
      </dl>
      <p className="login-brand-foot">Sichtbar ist nur, was Rolle und Bereich freigeben.</p>
    </section>
  );
}

/**
 * Render the React login island.
 */
export function LoginApp(): ReactNode {
  const [session, setSession] = useState(() => readStoredSession());
  const loggedIn = Boolean(session.token && session.user);
  useEffect(() => {
    /**
     * Sync the island when the existing auth runtime changes localStorage.
     */
    function handleAuthChange(): void {
      setSession(readStoredSession());
    }

    window.addEventListener("maintenance-auth-changed", handleAuthChange);
    return () => window.removeEventListener("maintenance-auth-changed", handleAuthChange);
  }, []);

  /**
   * Mark the React island as authenticated immediately after a successful login.
   */
  function handleLogin(data: LoginData): void {
    setSession({
      token: data.access_token,
      user: data.user,
      error: null
    });
  }

  return (
    <div className="login-screen">
      <LoginBrandPanel />
      <div className="login-panel">
        {loggedIn ? <LoggedInPanel /> : <LoginForm onLogin={handleLogin} />}
      </div>
    </div>
  );
}
