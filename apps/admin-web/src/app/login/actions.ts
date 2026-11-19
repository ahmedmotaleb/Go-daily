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
  const challenge = String(formData.get("challenge") ?? "");
  if (challenge) return codeStep(challenge, formData);
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
  if (result.twofa_required && result.challenge) {
    // Password accepted; ask for the code from the authenticator app.
    return { ok: false, values: { phone, challenge: result.challenge } };
  }
  return finish(result, formData);
}

/** Second step (U31): the code from the authenticator app, or a recovery code. */
async function codeStep(challenge: string, formData: FormData): Promise<FormState> {
  const code = String(formData.get("code") ?? "").trim();
  const phone = String(formData.get("phone") ?? "");
  if (!code) return { ok: false, message: "أدخل رمز التحقق", values: { phone, challenge } };
  let result: LoginResponse;
  try {
    result = await api.post<LoginResponse>(
      "/auth/login/2fa",
      { challenge, code },
      { anonymous: true },
    );
  } catch (error) {
    if (error instanceof ApiError) {
      // An expired challenge starts over from the password.
      const values: Record<string, string> = { phone };
      if (error.code !== "twofa_challenge_expired") values.challenge = challenge;
      return { ok: false, message: error.message, values };
    }
    throw error;
  }
  return finish(result, formData);
}

async function finish(result: LoginResponse, formData: FormData): Promise<FormState> {
  if (!result.access_token || !result.expires_at) {
    return { ok: false, message: "تعذر تسجيل الدخول، حاول مرة أخرى" };
  }
  await setSessionCookie(result.access_token, result.expires_at);
  redirect(safeNext(formData.get("next")));
}
