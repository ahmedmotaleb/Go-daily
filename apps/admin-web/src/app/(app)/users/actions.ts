"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { errorToFormState, formValues, str, strOrNull, bool } from "@/lib/form-state";
import type { FormState } from "@/lib/forms";
import type { User } from "@/lib/types";

export async function createUserAction(_: FormState, formData: FormData): Promise<FormState> {
  const values = formValues(formData);
  if (!str(formData, "role")) {
    return { ok: false, fieldErrors: { role: "اختر الصلاحية" }, values };
  }
  let created: User;
  try {
    created = await api.post<User>("/users", {
      full_name: str(formData, "full_name"),
      phone: str(formData, "phone"),
      email: str(formData, "email") ?? null,
      role: str(formData, "role"),
      password: formData.get("password"),
      is_active: bool(formData, "is_active"),
    });
  } catch (error) {
    return errorToFormState(error, values);
  }
  revalidatePath("/users");
  redirect(`/users/${created.id}?created=1`);
}

export async function updateUserAction(
  userId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  const values = formValues(formData);
  try {
    await api.patch<User>(`/users/${userId}`, {
      full_name: str(formData, "full_name"),
      phone: str(formData, "phone"),
      email: strOrNull(formData, "email"),
      role: str(formData, "role"),
    });
  } catch (error) {
    return errorToFormState(error, values);
  }
  revalidatePath("/users");
  revalidatePath(`/users/${userId}`);
  return { ok: true, message: "تم حفظ التعديلات" };
}

export async function setUserActiveAction(
  userId: string,
  active: boolean,
  _: FormState,
): Promise<FormState> {
  try {
    await api.patch<User>(`/users/${userId}`, { is_active: active });
  } catch (error) {
    return errorToFormState(error);
  }
  revalidatePath("/users");
  revalidatePath(`/users/${userId}`);
  return { ok: true, message: active ? "تم تفعيل الحساب" : "تم إيقاف الحساب وإنهاء جلساته" };
}

export async function resetPasswordAction(
  userId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  const password = String(formData.get("new_password") ?? "");
  const confirm = String(formData.get("confirm_password") ?? "");
  if (password !== confirm) {
    return { ok: false, fieldErrors: { confirm_password: "كلمتا المرور غير متطابقتين" } };
  }
  try {
    await api.post(`/users/${userId}/reset-password`, { new_password: password });
  } catch (error) {
    return errorToFormState(error);
  }
  return { ok: true, message: "تم تعيين كلمة المرور الجديدة وإنهاء جلسات المستخدم" };
}
