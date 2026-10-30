/** Safe readers for `searchParams` values (the API validates again). */

type SP = Record<string, string | string[] | undefined>;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const DATE = /^\d{4}-\d{2}-\d{2}$/;

export function spString(sp: SP, key: string): string | undefined {
  const v = sp[key];
  return typeof v === "string" && v.trim() !== "" ? v.trim() : undefined;
}

export function spUuid(sp: SP, key: string): string | undefined {
  const v = spString(sp, key);
  return v && UUID.test(v) ? v : undefined;
}

export function spDate(sp: SP, key: string): string | undefined {
  const v = spString(sp, key);
  return v && DATE.test(v) ? v : undefined;
}

export function spEnum<T extends string>(
  sp: SP,
  key: string,
  allowed: readonly T[],
): T | undefined {
  const v = spString(sp, key);
  return v && (allowed as readonly string[]).includes(v) ? (v as T) : undefined;
}

export function spPage(sp: SP): number {
  return Math.max(1, Number(sp.page) || 1);
}

/** YYYY-MM-DD of today in Cairo, optionally shifted by whole days. */
export function cairoToday(offsetDays = 0): string {
  const now = new Date(Date.now() + offsetDays * 86_400_000);
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Cairo" }).format(now);
}

export function firstOfMonth(): string {
  return `${cairoToday().slice(0, 8)}01`;
}
