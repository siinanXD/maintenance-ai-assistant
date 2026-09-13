/**
 * Return true when a value is an object payload.
 */
export function isObjectPayload(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Normalize list responses returned by legacy and envelope API endpoints.
 */
export function listData<TItem>(payload: unknown): TItem[] {
  if (Array.isArray(payload)) {
    return payload as TItem[];
  }

  if (!isObjectPayload(payload)) {
    return [];
  }

  if (Array.isArray(payload.data)) {
    return payload.data as TItem[];
  }

  if (isObjectPayload(payload.data) && Array.isArray(payload.data.items)) {
    return payload.data.items as TItem[];
  }

  if (Array.isArray(payload.items)) {
    return payload.items as TItem[];
  }

  return [];
}

/**
 * Normalize success-envelope responses while accepting legacy raw payloads.
 */
export function unwrapData<TData>(payload: unknown): TData {
  if (isObjectPayload(payload) && Object.prototype.hasOwnProperty.call(payload, "data")) {
    return payload.data as TData;
  }

  return payload as TData;
}
