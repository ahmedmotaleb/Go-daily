"use server";

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
