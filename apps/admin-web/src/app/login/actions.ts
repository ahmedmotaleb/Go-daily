"use server";

import { redirect } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { FormState } from "@/lib/forms";
import { setSessionCookie } from "@/lib/session";
import type { LoginResponse } from "@/lib/types";

function safeNext(next: FormDataEntryValue | null): string {
  // Only allow same-site relative paths (prevents open redirects).
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

export async function loginAction(_: FormState, formData: FormData): Promise<FormState> {
  const phone = String(formData.get("phone") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  if (!phone || !password) {
    return { ok: false, message: "أدخل رقم الهاتف وكلمة المرور", values: { phone } };
  }
  let result: LoginResponse;
  try {
    result = await api.post<LoginResponse>(
      "/auth/login",
      { phone, password, client: "web" },
      { anonymous: true },
    );
  } catch (error) {
    if (error instanceof ApiError) return { ok: false, message: error.message, values: { phone } };
    throw error;
  }
  await setSessionCookie(result.access_token, result.expires_at);
  redirect(safeNext(formData.get("next")));
}
