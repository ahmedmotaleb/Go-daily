/**
 * Values bound to server actions (`action.bind(null, ...)`) come back from
 * the client and can be tampered with. Validate them before using them in
 * an API path or a redirect.
 */
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export function boundId(value: unknown): string {
  if (typeof value !== "string" || !UUID.test(value)) throw new Error("invalid id");
  return value;
}

export function boundOneOf<T extends string>(value: unknown, allowed: readonly T[]): T {
  if (typeof value !== "string" || !(allowed as readonly string[]).includes(value)) {
    throw new Error("invalid value");
  }
  return value as T;
}

/** Internal detail pages only: no external URLs, no protocol-relative paths. */
export function boundReturnPath(value: unknown): string {
  if (
    typeof value !== "string" ||
    !/^\/(finance|maintenance|vehicles|drivers)(\/[a-z0-9-]+)+$/.test(value)
  ) {
    throw new Error("invalid return path");
  }
  return value;
}
