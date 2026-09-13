import type { MaintenanceUser } from "../auth/session";

export type LoginFormValues = {
  readonly login: string;
  readonly password: string;
};

export type LoginData = {
  readonly access_token: string;
  readonly user: MaintenanceUser;
};

export type LoginResponse = LoginData | {
  readonly success?: boolean;
  readonly data?: LoginData;
};

/**
 * Return true when a value has the login payload shape returned by the API.
 */
function isLoginData(value: unknown): value is LoginData {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }

  const candidate = value as Record<string, unknown>;
  return typeof candidate.access_token === "string"
    && typeof candidate.user === "object"
    && candidate.user !== null
    && !Array.isArray(candidate.user);
}

/**
 * Normalize wrapped and unwrapped login API responses into a single payload.
 */
export function normalizeLoginResponse(response: LoginResponse): LoginData {
  if (isLoginData(response)) {
    return response;
  }

  if (response.success === true && isLoginData(response.data)) {
    return response.data;
  }

  throw new Error("Die Anmeldedaten konnten nicht gelesen werden.");
}
