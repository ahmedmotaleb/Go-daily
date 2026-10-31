"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { errorToFormState, formValues } from "@/lib/form-state";
import type { FormState } from "@/lib/forms";
import { compact, decimal, int, text } from "@/lib/parse";
import type { Route } from "@/lib/types";

function stop(formData: FormData, prefix: string) {
  return compact({
    name: text(formData, `${prefix}_name`),
    latitude: decimal(formData, `${prefix}_lat`),
    longitude: decimal(formData, `${prefix}_lng`),
    radius_m: int(formData, `${prefix}_radius`),
  });
}

function intermediateStops(formData: FormData) {
  const names = formData.getAll("stop_name").map(String);
  const lats = formData.getAll("stop_lat").map(String);
  const lngs = formData.getAll("stop_lng").map(String);
  const radii = formData.getAll("stop_radius").map(String);
  return names
    .map((name, i) =>
      compact({
        name: name.trim() || undefined,
        latitude: lats[i]?.trim() || undefined,
        longitude: lngs[i]?.trim() || undefined,
        radius_m: radii[i]?.trim() ? Number(radii[i]) : undefined,
      }),
    )
    .filter((s) => s.name);
}

function routeBody(formData: FormData) {
  const days = formData
    .getAll("operating_days")
    .map(Number)
    .filter((d) => d >= 1 && d <= 7);
  return compact({
    name: text(formData, "name"),
    operation_type_id: text(formData, "operation_type_id"),
    trip_pattern: text(formData, "trip_pattern"),
    origin: stop(formData, "origin"),
    destination: stop(formData, "destination"),
    intermediate_stops: intermediateStops(formData),
    expected_distance_km: decimal(formData, "expected_distance_km") ?? null,
    expected_duration_minutes: int(formData, "expected_duration_minutes") ?? null,
    window_start: text(formData, "window_start") ?? null,
    window_end: text(formData, "window_end") ?? null,
    operating_days: days.length ? days : null,
    notes: text(formData, "notes") ?? null,
  });
}

/** Echo repeated fields (stops, weekdays) so the form can restore them after an error. */
function routeValues(formData: FormData) {
  return {
    ...formValues(formData),
    __stops: JSON.stringify(intermediateStops(formData)),
    __days: formData.getAll("operating_days").join(","),
  };
}

export async function createRouteAction(_: FormState, formData: FormData): Promise<FormState> {
  const values = routeValues(formData);
  let route: Route;
  try {
    route = await api.post<Route>("/routes", routeBody(formData));
  } catch (error) {
    return errorToFormState(error, values);
  }
  revalidatePath("/operations");
  redirect(`/operations/routes/${route.id}?notice=created`);
}

export async function updateRouteAction(
  routeId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  const values = routeValues(formData);
  const body: Record<string, unknown> = routeBody(formData);
  delete body.operation_type_id; // the type of an existing route is fixed
  try {
    await api.patch<Route>(`/routes/${routeId}`, body);
  } catch (error) {
    return errorToFormState(error, values);
  }
  revalidatePath("/operations");
  revalidatePath(`/operations/routes/${routeId}`);
  return { ok: true, message: "تم حفظ المسار" };
}

export async function setRouteActiveAction(routeId: string, active: boolean): Promise<FormState> {
  try {
    await api.post(`/routes/${routeId}/${active ? "activate" : "deactivate"}`);
  } catch (error) {
    return errorToFormState(error);
  }
  revalidatePath("/operations");
  revalidatePath(`/operations/routes/${routeId}`);
  return { ok: true, message: active ? "تم تفعيل المسار" : "تم إيقاف المسار" };
}
