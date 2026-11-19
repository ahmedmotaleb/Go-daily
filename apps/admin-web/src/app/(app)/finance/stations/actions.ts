"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { boundId } from "@/lib/bound";
import { errorToFormState, formValues } from "@/lib/form-state";
import type { FormState } from "@/lib/forms";
import { checkbox, decimal, int, textOrNull } from "@/lib/parse";

function body(formData: FormData) {
  const latitude = decimal(formData, "latitude");
  const longitude = decimal(formData, "longitude");
  return {
    name: textOrNull(formData, "name"),
    brand: textOrNull(formData, "brand"),
    address: textOrNull(formData, "address"),
    latitude: latitude ?? null,
    longitude: longitude ?? null,
    radius_m: int(formData, "radius_m") ?? 150,
    is_trusted: checkbox(formData, "is_trusted"),
    fuel_type_ids: [...formData.keys()]
      .filter((k) => k.startsWith("fuel_type:"))
      .map((k) => k.slice("fuel_type:".length)),
    notes: textOrNull(formData, "notes"),
  };
}

export async function saveStationAction(
  id: string | null,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  if (id !== null) id = boundId(id);
  let saved: { id: string };
  try {
    saved = id
      ? await api.patch(`/fuel-stations/${id}`, body(formData))
      : await api.post("/fuel-stations", body(formData));
  } catch (error) {
    return errorToFormState(error, formValues(formData));
  }
  revalidatePath("/finance/stations");
  redirect(`/finance/stations/${saved.id}?notice=${id ? "record_updated" : "created"}`);
}

export async function toggleStationAction(
  id: string,
  active: boolean,
  _state: FormState,
  _formData: FormData,
): Promise<FormState> {
  id = boundId(id);
  try {
    await api.patch(`/fuel-stations/${id}`, { is_active: active === true });
  } catch (error) {
    return errorToFormState(error);
  }
  revalidatePath("/finance/stations");
  redirect(`/finance/stations/${id}?notice=record_updated`);
}
