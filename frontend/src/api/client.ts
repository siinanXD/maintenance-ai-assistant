type ApiRequestOptions = {
  readonly method?: string;
  readonly body?: unknown;
  readonly headers?: HeadersInit;
  readonly signal?: AbortSignal;
};

type ApiErrorPayload = {
  readonly error?: string;
  readonly message?: string;
};

class ApiRequestError extends Error {
  readonly status: number;

  readonly payload: ApiErrorPayload | null;

  /**
   * Create a typed API error from an unsuccessful fetch response.
   */
  constructor(message: string, status: number, payload: ApiErrorPayload | null) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.payload = payload;
  }
}

/**
 * Return true when a value is a plain object that can be used as JSON payload.
 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Read the stored JWT token used by the existing Flask/Jinja frontend.
 */
function readStoredToken(): string | null {
  return window.localStorage.getItem("maintenance_access_token");
}

/**
 * Build request headers compatible with the existing backend API.
 */
function buildHeaders(body: unknown, headers: HeadersInit | undefined): Headers {
  const requestHeaders = new Headers(headers);
  const token = readStoredToken();

  if (token) {
    requestHeaders.set("Authorization", `Bearer ${token}`);
  }

  if (body !== undefined && !(body instanceof FormData) && !requestHeaders.has("Content-Type")) {
    requestHeaders.set("Content-Type", "application/json");
  }

  return requestHeaders;
}

/**
 * Convert an optional request body into a fetch-compatible body.
 */
function serializeBody(body: unknown): BodyInit | null {
  if (body === undefined || body === null) {
    return null;
  }

  if (body instanceof FormData || typeof body === "string" || body instanceof Blob) {
    return body;
  }

  return JSON.stringify(body);
}

/**
 * Parse a JSON response, returning null for empty bodies.
 */
async function parseJsonResponse(response: Response): Promise<unknown> {
  const text = await response.text();

  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text) as unknown;
  } catch (error) {
    throw new ApiRequestError("Die Serverantwort konnte nicht gelesen werden.", response.status, {
      error: "invalid_json",
      message: error instanceof Error ? error.message : "Invalid JSON response"
    });
  }
}

/**
 * Resolve the safest user-facing error message from an API payload.
 */
function errorMessageFromPayload(payload: unknown, fallback: string): string {
  if (!isRecord(payload)) {
    return fallback;
  }

  const message = payload.message;
  const error = payload.error;

  if (typeof message === "string" && message.trim()) {
    return message;
  }

  if (typeof error === "string" && error.trim()) {
    return error;
  }

  return fallback;
}

/**
 * Call an existing `/api/v1/...` endpoint using the shared auth storage contract.
 */
export async function apiRequest<TResponse>(
  path: string,
  options: ApiRequestOptions = {}
): Promise<TResponse> {
  if (!path.startsWith("/api/")) {
    throw new Error(`API paths must start with /api/: ${path}`);
  }

  const response = await fetch(path, {
    method: options.method ?? "GET",
    headers: buildHeaders(options.body, options.headers),
    body: serializeBody(options.body),
    signal: options.signal
  });
  const payload = await parseJsonResponse(response);

  if (!response.ok) {
    throw new ApiRequestError(
      errorMessageFromPayload(payload, "Die Anfrage konnte nicht verarbeitet werden."),
      response.status,
      isRecord(payload) ? payload : null
    );
  }

  return payload as TResponse;
}
