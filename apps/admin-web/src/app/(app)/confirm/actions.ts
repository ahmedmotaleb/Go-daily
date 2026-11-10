"use server";

import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { errorToFormState } from "@/lib/form-state";
import type { FormState } from "@/lib/forms";

function safeNext(next: FormDataEntryValue | null): string {
  if (
    typeof next === "string" &&
    next.startsWith("/") &&
    !next.startsWith("//") &&
    !next.startsWith("/\\")
  ) {
    return next;
  }
  return "/";
}

/** U35: confirm the password (and 2FA code), then go back to the sensitive action. */
export async function confirmAction(_: FormState, formData: FormData): Promise<FormState> {
  const code = String(formData.get("code") ?? "").trim();
  try {
    await api.post("/auth/reauth", {
      password: String(formData.get("password") ?? ""),
      ...(code ? { code } : {}),
    });
  } catch (error) {
    return errorToFormState(error);
  }
  redirect(safeNext(formData.get("next")));
}
