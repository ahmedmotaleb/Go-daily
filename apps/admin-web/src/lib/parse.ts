import { cairoLocalToIso } from "./time";

/** FormData parsing helpers shared by server actions. */

export function text(formData: FormData, key: string): string | undefined {
  const v = formData.get(key);
  if (typeof v !== "string") return undefined;
  const t = v.trim();
  return t === "" ? undefined : t;
}

/** For PATCH: empty -> null (clears an optional field). */
export function textOrNull(formData: FormData, key: string): string | null {
  return text(formData, key) ?? null;
}

/** Integer field; empty -> undefined; invalid -> the raw string (the API returns a 422). */
export function int(formData: FormData, key: string): number | string | undefined {
  const t = text(formData, key);
  if (t === undefined) return undefined;
  const normalized = t
    .replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d)))
    .replace(/[,\s]/g, "");
  return /^-?\d+$/.test(normalized) ? Number(normalized) : t;
}

export function intOrNull(formData: FormData, key: string): number | string | null {
  return int(formData, key) ?? null;
}

/** Decimal kept as a string (money is never parsed into a float). */
export function decimal(formData: FormData, key: string): string | undefined {
  const t = text(formData, key);
  if (t === undefined) return undefined;
  return t
    .replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d)))
    .replace(/٫/g, ".")
    .replace(/[,\s]/g, "");
}

export function checkbox(formData: FormData, key: string): boolean {
  const v = formData.get(key);
  return v === "on" || v === "true";
}

/** datetime-local (Cairo wall time) -> ISO instant. */
export function datetime(formData: FormData, key: string): string | undefined {
  return cairoLocalToIso(text(formData, key));
}

/** Drop undefined values so they are not sent to the API. */
export function compact<T extends Record<string, unknown>>(obj: T): Partial<T> {
  return Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== undefined)) as Partial<T>;
}
