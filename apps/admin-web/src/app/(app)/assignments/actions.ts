"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { errorToFormState, formValues } from "@/lib/form-state";
import type { FormState } from "@/lib/forms";
import { safeReturnPath, withNotice } from "@/lib/notices";
import { checkbox, compact, datetime, text } from "@/lib/parse";

function revalidateBoth(driverId?: string, vehicleId?: string) {
  if (driverId) revalidatePath(`/drivers/${driverId}`);
  if (vehicleId) revalidatePath(`/vehicles/${vehicleId}`);
  revalidatePath("/vehicles");
  revalidatePath("/drivers");
}

export async function createAssignmentAction(_: FormState, formData: FormData): Promise<FormState> {
  const values = formValues(formData);
  const driverId = text(formData, "driver_id");
  const vehicleId = text(formData, "vehicle_id");
  if (!driverId || !vehicleId) {
    return {
      ok: false,
      fieldErrors: driverId ? { vehicle_id: "اختر المركبة" } : { driver_id: "اختر السائق" },
      values,
    };
  }
  try {
    await api.post(
      "/assignments",
      compact({
        driver_id: driverId,
        vehicle_id: vehicleId,
        role: text(formData, "role") ?? "PRIMARY",
        starts_at: datetime(formData, "starts_at"),
        notes: text(formData, "notes"),
        replace_current: checkbox(formData, "replace_current"),
      }),
    );
  } catch (error) {
    return errorToFormState(error, values);
  }
  revalidateBoth(driverId, vehicleId);
  redirect(
    withNotice(
      safeReturnPath(formData.get("return_to"), `/vehicles/${vehicleId}`),
      "assignment_created",
    ),
  );
}

export async function endAssignmentAction(
  assignmentId: string,
  driverId: string,
  vehicleId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  try {
    await api.post(
      `/assignments/${assignmentId}/end`,
      compact({
        ends_at: datetime(formData, "ends_at"),
        notes: text(formData, "notes"),
      }),
    );
  } catch (error) {
    return errorToFormState(error);
  }
  revalidateBoth(driverId, vehicleId);
  redirect(
    withNotice(
      safeReturnPath(formData.get("return_to"), `/vehicles/${vehicleId}`),
      "assignment_ended",
    ),
  );
}
