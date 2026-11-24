"use server";

import { revalidatePath } from "next/cache";
import QRCode from "qrcode";
import { api } from "@/lib/api";
import { errorToFormState } from "@/lib/form-state";
import type { FormState } from "@/lib/forms";

export async function changePasswordAction(_: FormState, formData: FormData): Promise<FormState> {
  const current = String(formData.get("current_password") ?? "");
  const next = String(formData.get("new_password") ?? "");
  if (next !== String(formData.get("confirm_password") ?? "")) {
    return { ok: false, fieldErrors: { confirm_password: "كلمتا المرور غير متطابقتين" } };
  }
  try {
    await api.post("/auth/change-password", { current_password: current, new_password: next });
  } catch (error) {
    return errorToFormState(error);
  }
  return { ok: true, message: "تم تغيير كلمة المرور وإنهاء جلساتك الأخرى" };
}

/** Two-factor login (U31). Secrets and codes are shown once and never stored in the web app. */
export type TwoFactorState = {
  stage?: "scan" | "codes";
  qr?: string;
  secret?: string;
  codes?: string[];
  error?: string;
  fieldErrors?: Record<string, string>;
};

function failure(error: unknown, keep: TwoFactorState = {}): TwoFactorState {
  const state = errorToFormState(error);
  return { ...keep, error: state.message, fieldErrors: state.fieldErrors };
}

/** One flow for setup: "start" shows the QR code, then the code enables it. */
export async function twoFactorFlowAction(
  prev: TwoFactorState,
  formData: FormData,
): Promise<TwoFactorState> {
  if (formData.get("op") === "start") return twoFactorSetup();
  return twoFactorEnable(prev, formData);
}

async function twoFactorSetup(): Promise<TwoFactorState> {
  try {
    const res = await api.post<{ secret: string; otpauth_uri: string }>("/auth/2fa/setup", {});
    const svg = await QRCode.toString(res.otpauth_uri, { type: "svg", margin: 1, width: 200 });
    const qr = `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`;
    return { stage: "scan", qr, secret: res.secret };
  } catch (error) {
    return failure(error);
  }
}

async function twoFactorEnable(prev: TwoFactorState, formData: FormData): Promise<TwoFactorState> {
  try {
    const res = await api.post<{ recovery_codes: string[] }>("/auth/2fa/enable", {
      code: String(formData.get("code") ?? "").trim(),
    });
    // No revalidation here: the codes must stay on screen until the user
    // confirms they saved them (the card then refreshes the page).
    return { stage: "codes", codes: res.recovery_codes };
  } catch (error) {
    return failure(error, { stage: prev.stage, qr: prev.qr, secret: prev.secret });
  }
}

function reauth(formData: FormData) {
  return {
    password: String(formData.get("password") ?? ""),
    code: String(formData.get("code") ?? "").trim(),
  };
}

export async function twoFactorCodesAction(
  _: TwoFactorState,
  formData: FormData,
): Promise<TwoFactorState> {
  try {
    const res = await api.post<{ recovery_codes: string[] }>(
      "/auth/2fa/recovery-codes",
      reauth(formData),
    );
    return { stage: "codes", codes: res.recovery_codes };
  } catch (error) {
    return failure(error);
  }
}

export async function twoFactorDisableAction(
  _: TwoFactorState,
  formData: FormData,
): Promise<TwoFactorState> {
  try {
    await api.post("/auth/2fa/disable", reauth(formData));
  } catch (error) {
    return failure(error);
  }
  revalidatePath("/account");
  return {};
}
