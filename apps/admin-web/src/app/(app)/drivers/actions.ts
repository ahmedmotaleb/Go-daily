"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { errorToFormState, formValues } from "@/lib/form-state";
import type { FormState } from "@/lib/forms";
import { withNotice } from "@/lib/notices";
import { compact, decimal, text, textOrNull } from "@/lib/parse";
import type { Driver } from "@/lib/types";

function revalidate(driverId?: string) {
  revalidatePath("/drivers");
  if (driverId) revalidatePath(`/drivers/${driverId}`);
}

export async function createDriverAction(_: FormState, formData: FormData): Promise<FormState> {
  const values = formValues(formData);
  let driver: Driver;
  try {
    driver = await api.post<Driver>(
      "/drivers",
      compact({
        full_name: text(formData, "full_name"),
        phone: text(formData, "phone"),
        national_id: text(formData, "national_id"),
        license_number: text(formData, "license_number"),
        license_expiry: text(formData, "license_expiry"),
        employment_status: text(formData, "employment_status"),
        hire_date: text(formData, "hire_date"),
        notes: text(formData, "notes"),
      }),
    );
  } catch (error) {
    return errorToFormState(error, values);
  }
  revalidate();
  redirect(`/drivers/${driver.id}?created=1`);
}

export async function updateDriverAction(
  driverId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  const values = formValues(formData);
  const body: Record<string, unknown> = compact({
    full_name: text(formData, "full_name"),
    phone: text(formData, "phone"),
    license_number: textOrNull(formData, "license_number"),
    license_expiry: textOrNull(formData, "license_expiry"),
    employment_status: text(formData, "employment_status"),
    hire_date: textOrNull(formData, "hire_date"),
    end_date: textOrNull(formData, "end_date"),
    notes: textOrNull(formData, "notes"),
  });
  // The national ID is write-only in this form: blank keeps the stored value.
  const nid = text(formData, "national_id");
  if (nid) body.national_id = nid;
  if (formData.get("clear_national_id") === "on") body.national_id = null;
  try {
    await api.patch<Driver>(`/drivers/${driverId}`, body);
  } catch (error) {
    return errorToFormState(error, values);
  }
  revalidate(driverId);
  return { ok: true, message: "تم حفظ بيانات السائق" };
}

export async function revealNationalIdAction(driverId: string): Promise<FormState> {
  try {
    const res = await api.get<{ national_id: string | null }>(`/drivers/${driverId}/sensitive`);
    return {
      ok: true,
      message: res.national_id ? `الرقم القومي: ${res.national_id}` : "لا يوجد رقم قومي مسجل",
    };
  } catch (error) {
    return errorToFormState(error);
  }
}

export async function createDriverAccountAction(
  driverId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  const password = String(formData.get("password") ?? "");
  if (password !== String(formData.get("confirm_password") ?? "")) {
    return { ok: false, fieldErrors: { confirm_password: "كلمتا المرور غير متطابقتين" } };
  }
  try {
    await api.post(`/drivers/${driverId}/account`, { password });
  } catch (error) {
    return errorToFormState(error);
  }
  revalidate(driverId);
  redirect(withNotice(`/drivers/${driverId}`, "account_created"));
}

export async function resetDriverPasswordAction(
  driverId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  const password = String(formData.get("new_password") ?? "");
  if (password !== String(formData.get("confirm_password") ?? "")) {
    return { ok: false, fieldErrors: { confirm_password: "كلمتا المرور غير متطابقتين" } };
  }
  try {
    await api.post(`/drivers/${driverId}/account/reset-password`, { new_password: password });
  } catch (error) {
    return errorToFormState(error);
  }
  return { ok: true, message: "تم تعيين كلمة مرور جديدة وإنهاء جلسات التطبيق" };
}

export async function setDriverAccountActiveAction(
  driverId: string,
  active: boolean,
): Promise<FormState> {
  try {
    await api.post(`/drivers/${driverId}/account/${active ? "activate" : "deactivate"}`);
  } catch (error) {
    return errorToFormState(error);
  }
  revalidate(driverId);
  redirect(
    withNotice(`/drivers/${driverId}`, active ? "account_activated" : "account_deactivated"),
  );
}

export async function addCompensationPlanAction(
  driverId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  const values = formValues(formData);
  const method = text(formData, "method");
  const body = compact({
    method,
    effective_from: text(formData, "effective_from"),
    notes: text(formData, "notes"),
    fixed_monthly_amount:
      method === "FIXED_MONTHLY" || method === "FIXED_PLUS_INCENTIVE"
        ? decimal(formData, "fixed_monthly_amount")
        : undefined,
    daily_wage_amount: method === "DAILY_WAGE" ? decimal(formData, "daily_wage_amount") : undefined,
    revenue_percentage:
      method === "REVENUE_PERCENTAGE" ? decimal(formData, "revenue_percentage") : undefined,
    incentive_percentage:
      method === "FIXED_PLUS_INCENTIVE" ? decimal(formData, "incentive_percentage") : undefined,
    incentive_threshold_amount:
      method === "FIXED_PLUS_INCENTIVE"
        ? decimal(formData, "incentive_threshold_amount")
        : undefined,
  });
  try {
    await api.post(`/drivers/${driverId}/compensation-plans`, body);
  } catch (error) {
    return errorToFormState(error, values);
  }
  revalidate(driverId);
  return { ok: true, message: "تمت إضافة خطة الاحتساب الجديدة وإغلاق الخطة السابقة" };
}
