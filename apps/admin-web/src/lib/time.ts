import { DISPLAY_TIMEZONE } from "./format";

/**
 * Helpers for <input type="datetime-local"> values, which carry no
 * timezone. The UI treats them as Africa/Cairo wall time.
 */

function tzOffsetMinutes(instant: Date, timeZone: string): number {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    })
      .formatToParts(instant)
      .map((p) => [p.type, p.value]),
  );
  const asUtc = Date.UTC(
    Number(parts.year),
    Number(parts.month) - 1,
    Number(parts.day),
    Number(parts.hour),
    Number(parts.minute),
    Number(parts.second),
  );
  return Math.round((asUtc - instant.getTime()) / 60_000);
}

/** "2026-03-01T08:30" (Cairo wall time) -> ISO instant with offset, or undefined if empty/invalid. */
export function cairoLocalToIso(
  value: string | null | undefined,
  timeZone = DISPLAY_TIMEZONE,
): string | undefined {
  if (!value) return undefined;
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(value);
  if (!m) return undefined;
  const [, y, mo, d, h, mi, s] = m;
  const wallAsUtc = Date.UTC(
    Number(y),
    Number(mo) - 1,
    Number(d),
    Number(h),
    Number(mi),
    Number(s ?? 0),
  );
  // Two passes handle DST transitions.
  let instant = wallAsUtc - tzOffsetMinutes(new Date(wallAsUtc), timeZone) * 60_000;
  instant = wallAsUtc - tzOffsetMinutes(new Date(instant), timeZone) * 60_000;
  return new Date(instant).toISOString();
}

/** ISO instant -> "YYYY-MM-DDTHH:mm" in Cairo wall time (for input defaults). */
export function isoToCairoLocal(
  iso: string | null | undefined,
  timeZone = DISPLAY_TIMEZONE,
): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const shifted = new Date(date.getTime() + tzOffsetMinutes(date, timeZone) * 60_000);
  return shifted.toISOString().slice(0, 16);
}
