"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { errorToFormState, formValues } from "@/lib/form-state";
import type { FormState } from "@/lib/forms";
import { compact, text } from "@/lib/parse";

export async function generateRunsAction(_: FormState, formData: FormData): Promise<FormState> {
  const values = formValues(formData);
  const days = formData
    .getAll("weekdays")
    .map(Number)
    .filter((d) => d >= 1 && d <= 7);
  let created = 0;
  try {
    const res = await api.post<{ created: number }>(
      "/school-runs/generate",
      compact({
        route_id: text(formData, "route_id"),
        vehicle_id: text(formData, "vehicle_id"),
        driver_id: text(formData, "driver_id"),
        date_from: text(formData, "date_from"),
        date_to: text(formData, "date_to"),
        start_time: text(formData, "start_time"),
        end_time: text(formData, "end_time"),
        label: text(formData, "label"),
        weekdays: days.length ? days : undefined,
      }),
    );
    created = res.created;
  } catch (error) {
    return errorToFormState(error, values);
  }
  revalidatePath("/operations/school-runs");
  return { ok: true, message: `تم إنشاء ${created} دورة مجدولة (يتم تخطي الدورات الموجودة).` };
}

export async function correctRunStatusAction(
  runId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  try {
    await api.post(`/school-runs/${runId}/status`, {
      status: text(formData, "status"),
      reason: text(formData, "reason") ?? "",
    });
  } catch (error) {
    return errorToFormState(error);
  }
  revalidatePath("/operations/school-runs");
  const day = text(formData, "day");
  redirect(`/operations/school-runs?notice=status_corrected${day ? `&day=${day}` : ""}`);
}
