import "server-only";
import { ApiError } from "./api";
import type { FormState } from "./forms";

export function formValues(formData: FormData): Record<string, string> {
  const out: Record<string, string> = {};
  formData.forEach((value, key) => {
    if (typeof value === "string" && !key.startsWith("$ACTION") && !/password/i.test(key)) {
      out[key] = value;
    }
  });
  return out;
}

/** Convert an API error into form state (maps 422 field errors to inputs). Rethrows anything else. */
export function errorToFormState(error: unknown, values?: Record<string, string>): FormState {
  if (error instanceof ApiError) {
    const fieldErrors: Record<string, string> = {};
    for (const f of error.body.details?.fields ?? []) {
      const name = f.loc.filter((p) => p !== "body").join(".");
      if (name && !fieldErrors[name]) fieldErrors[name] = f.msg.replace(/^Value error, /, "");
    }
    return { ok: false, message: error.message, fieldErrors, values };
  }
  throw error;
}

/** Trimmed string field; empty -> undefined. */
export function str(formData: FormData, key: string): string | undefined {
  const v = formData.get(key);
  if (typeof v !== "string") return undefined;
  const t = v.trim();
  return t === "" ? undefined : t;
}

/** Trimmed string field; empty -> null (to clear optional values on update). */
export function strOrNull(formData: FormData, key: string): string | null {
  return str(formData, key) ?? null;
}

export function bool(formData: FormData, key: string): boolean {
  const v = formData.get(key);
  return v === "on" || v === "true" || v === "1";
}
