"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { errorToFormState, formValues } from "@/lib/form-state";
import type { FormState } from "@/lib/forms";
import { withNotice } from "@/lib/notices";
import { compact, int, intOrNull, text, textOrNull } from "@/lib/parse";
import type { Vehicle } from "@/lib/types";

function vehicleFields(formData: FormData, forUpdate: boolean) {
  const opt = forUpdate ? textOrNull : text;
  return {
    internal_code: text(formData, "internal_code"),
    plate_number: text(formData, "plate_number"),
    vehicle_type_id: text(formData, "vehicle_type_id"),
    manufacturer: opt(formData, "manufacturer"),
    model: opt(formData, "model"),
    model_year: forUpdate ? intOrNull(formData, "model_year") : int(formData, "model_year"),
    color: opt(formData, "color"),
    ownership_status: text(formData, "ownership_status"),
    current_odometer_km: forUpdate
      ? intOrNull(formData, "current_odometer_km")
      : int(formData, "current_odometer_km"),
    license_expiry: opt(formData, "license_expiry"),
    insurance_expiry: opt(formData, "insurance_expiry"),
    notes: opt(formData, "notes"),
  };
}

export async function createVehicleAction(_: FormState, formData: FormData): Promise<FormState> {
  const values = formValues(formData);
  let vehicle: Vehicle;
  try {
    vehicle = await api.post<Vehicle>("/vehicles", compact(vehicleFields(formData, false)));
  } catch (error) {
    return errorToFormState(error, values);
  }
  revalidatePath("/vehicles");
  redirect(`/vehicles/${vehicle.id}?created=1`);
}

export async function updateVehicleAction(
  vehicleId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  const values = formValues(formData);
  const body = compact({
    ...vehicleFields(formData, true),
    odometer_correction_reason: text(formData, "odometer_correction_reason"),
  });
  try {
    await api.patch<Vehicle>(`/vehicles/${vehicleId}`, body);
  } catch (error) {
    return errorToFormState(error, values);
  }
  revalidatePath("/vehicles");
  revalidatePath(`/vehicles/${vehicleId}`);
  return { ok: true, message: "تم حفظ بيانات المركبة" };
}

export async function setVehicleActiveAction(
  vehicleId: string,
  active: boolean,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  try {
    await api.post<Vehicle>(`/vehicles/${vehicleId}/${active ? "activate" : "deactivate"}`, {
      reason: text(formData, "reason") ?? null,
    });
  } catch (error) {
    return errorToFormState(error);
  }
  revalidatePath("/vehicles");
  revalidatePath(`/vehicles/${vehicleId}`);
  redirect(
    withNotice(`/vehicles/${vehicleId}`, active ? "vehicle_activated" : "vehicle_deactivated"),
  );
}
