/**
 * Display formatting for the Arabic (Egypt) UI.
 *
 * - Times are stored in UTC by the API and shown in Africa/Cairo.
 * - Latin digits are used for numbers so plates, odometers and amounts
 *   read the same as on paper receipts and in input fields.
 */

export const DISPLAY_TIMEZONE = "Africa/Cairo";
const LOCALE = "ar-EG-u-nu-latn";

const moneyFormatter = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: "EGP",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const numberFormatter = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 3 });

const dateFormatter = new Intl.DateTimeFormat(LOCALE, {
  timeZone: DISPLAY_TIMEZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const dateTimeFormatter = new Intl.DateTimeFormat(LOCALE, {
  timeZone: DISPLAY_TIMEZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: true,
});

/** Money arrives from the API as a decimal string; never do arithmetic on the result. */
export function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? moneyFormatter.format(n) : "—";
}

export function formatNumber(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? numberFormatter.format(n) : "—";
}

function toDate(value: string | Date): Date | null {
  const d = typeof value === "string" ? new Date(value) : value;
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return "—";
  // Plain calendar dates (YYYY-MM-DD) are not instants; do not shift them by timezone.
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [y, m, d] = value.split("-");
    return `${d}/${m}/${y}`;
  }
  const d = toDate(value);
  return d ? dateFormatter.format(d) : "—";
}

export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const d = toDate(value);
  return d ? dateTimeFormatter.format(d) : "—";
}

/** Whole days from `today` until a calendar date (negative when past). */
export function daysUntil(isoDate: string, today: Date = new Date()): number {
  const [y, m, d] = isoDate.split("-").map(Number) as [number, number, number];
  const target = Date.UTC(y, m - 1, d);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: DISPLAY_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  })
    .format(today)
    .split("-")
    .map(Number) as [number, number, number];
  const base = Date.UTC(parts[0], parts[1] - 1, parts[2]);
  return Math.round((target - base) / 86_400_000);
}
