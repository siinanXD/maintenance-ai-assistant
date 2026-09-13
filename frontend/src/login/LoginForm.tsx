import { useState, type FormEvent, type ReactNode } from "react";

import { apiRequest } from "../api/client";
import { legacyAuthRuntime } from "../app/runtimeBridge";
import { safeErrorMessage } from "../utils/errors";
import { normalizeLoginResponse, type LoginData, type LoginFormValues, type LoginResponse } from "./loginTypes";

type LoginFormProps = {
  readonly onLogin: (data: LoginData) => void;
};

type MessageState = {
  readonly text: string;
  readonly variant: "success" | "error" | "info" | null;
};

const EMPTY_MESSAGE: MessageState = { text: "", variant: null };

/**
 * Return a login destination that is compatible with the existing auth runtime.
 */
function loginDestination(user: LoginData["user"], nextPath: string | null): string {
  const maintenanceAuth = legacyAuthRuntime();

  if (maintenanceAuth && typeof maintenanceAuth.destinationForUserOrNext === "function") {
    return maintenanceAuth.destinationForUserOrNext(user, nextPath);
  }

  return nextPath || "/";
}

/**
 * Return the safest user-facing message for a failed login attempt.
 */
function loginErrorMessage(error: unknown): string {
  return safeErrorMessage(error, "Anmeldung fehlgeschlagen.");
}

/**
 * Persist the login result using the existing localStorage auth contract.
 */
function persistLogin(data: LoginData): void {
  window.localStorage.setItem("maintenance_access_token", data.access_token);
  window.localStorage.setItem("maintenance_user", JSON.stringify(data.user));
  window.dispatchEvent(new Event("maintenance-auth-changed"));
}

/**
 * Validate the login form before it calls the backend.
 */
function validateLogin(values: LoginFormValues): string | null {
  if (!values.login || !values.password) {
    return "Bitte Benutzername/E-Mail und Passwort eingeben.";
  }

  return null;
}

/**
 * Submit credentials to the existing Flask auth API.
 */
async function submitLogin(values: LoginFormValues): Promise<LoginData> {
  const validationError = validateLogin(values);

  if (validationError) {
    throw new Error(validationError);
  }

  const response = await apiRequest<LoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: {
      login: values.login,
      password: values.password
    }
  });

  return normalizeLoginResponse(response);
}

/**
 * Render the React login form with the same hooks and classes as the Jinja fallback.
 */
export function LoginForm({ onLogin }: LoginFormProps): ReactNode {
  const [values, setValues] = useState<LoginFormValues>({ login: "", password: "" });
  const [message, setMessage] = useState<MessageState>(EMPTY_MESSAGE);
  const [busy, setBusy] = useState(false);
  const loginInvalid = message.variant === "error" && !values.login;
  const passwordInvalid = message.variant === "error" && !values.password;

  /**
   * Handle a controlled input update.
   */
  function updateField(fieldName: keyof LoginFormValues, value: string): void {
    setValues((currentValues) => ({ ...currentValues, [fieldName]: value }));
    if (message.variant === "error") {
      setMessage(EMPTY_MESSAGE);
    }
  }

  /**
   * Handle form submission and redirect after successful authentication.
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setMessage({ text: "Anmeldung wird geprüft...", variant: "info" });

    try {
      const data = await submitLogin({
        login: values.login.trim(),
        password: values.password
      });
      persistLogin(data);
      setMessage({ text: "Anmeldung erfolgreich. Du wirst weitergeleitet...", variant: "success" });
      onLogin(data);

      const nextPath = new URLSearchParams(window.location.search).get("next");
      window.location.href = loginDestination(data.user, nextPath);
    } catch (error) {
      setMessage({ text: loginErrorMessage(error), variant: "error" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="login-card" method="post" action="/api/v1/auth/login" data-login-form onSubmit={handleSubmit}>
      <p className="page-kicker">Anmelden</p>
      <h2 className="login-card-title">Willkommen zurück</h2>
      <p className="login-card-meta">Mit Benutzername oder E-Mail und Passwort.</p>
      <div className="login-fields">
        <div className="field">
          <label htmlFor="react-login">Benutzername oder E-Mail</label>
          <input
            aria-invalid={loginInvalid}
            className="input input-bordered"
            disabled={busy}
            id="react-login"
            name="login"
            onChange={(event) => updateField("login", event.target.value)}
            autoComplete="username"
            placeholder="name@firma.de"
            value={values.login}
          />
        </div>
        <div className="field">
          <label htmlFor="react-password">Passwort</label>
          <input
            aria-invalid={passwordInvalid}
            className="input input-bordered"
            disabled={busy}
            id="react-password"
            name="password"
            onChange={(event) => updateField("password", event.target.value)}
            autoComplete="current-password"
            placeholder="Passwort"
            type="password"
            value={values.password}
          />
        </div>
      </div>
      <button className="btn btn-primary login-submit" disabled={busy} type="submit">
        {busy ? "Anmelden..." : "Anmelden"}
      </button>
      <p className={`panel-meta login-message${message.variant ? ` is-${message.variant}` : ""}`} data-login-message role="status">
        {message.text}
      </p>
      <a className="login-secondary-link" href="/api-docs">API-Protokoll ansehen</a>
    </form>
  );
}
