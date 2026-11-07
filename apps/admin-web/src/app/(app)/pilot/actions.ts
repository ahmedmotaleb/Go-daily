"use server";

import { revalidatePath } from "next/cache";
import { api } from "@/lib/api";
import { errorToFormState } from "@/lib/form-state";
import type { FormState } from "@/lib/forms";
import { text } from "@/lib/parse";

/** Marks a vehicle as part of the pilot, or removes it (audited by the API). */
async function setPilot(vehicleId: string, pilot: boolean): Promise<FormState> {
  try {
    await api.patch(`/vehicles/${vehicleId}`, { pilot });
  } catch (error) {
    return errorToFormState(error, {});
  }
  revalidatePath("/pilot");
  return { ok: true, message: pilot ? "أُضيفت السيارة للتجربة" : "أُزيلت من التجربة" };
}

export async function addPilotAction(_: FormState, formData: FormData): Promise<FormState> {
  const vehicleId = text(formData, "vehicle_id");
  if (!vehicleId) return { fieldErrors: { vehicle_id: "اختر السيارة" } };
  return setPilot(vehicleId, true);
}

export async function removePilotAction(
  vehicleId: string,
  _state: FormState,
  _formData: FormData,
): Promise<FormState> {
  return setPilot(vehicleId, false);
}
