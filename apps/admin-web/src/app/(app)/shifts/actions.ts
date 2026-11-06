"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { errorToFormState, formValues } from "@/lib/form-state";
import type { FormState } from "@/lib/forms";
import { compact, datetime, int, text } from "@/lib/parse";
import type { Shift } from "@/lib/types";

/** "typeId|routeId" (route optional) from the combined operation select. */
function operation(formData: FormData, key: string) {
  const raw = text(formData, key);
  if (!raw) return { operation_type_id: undefined, route_id: undefined };
  const [typeId, routeId] = raw.split("|");
  return { operation_type_id: typeId || undefined, route_id: routeId || undefined };
}

function refresh(shiftId?: string) {
  revalidatePath("/shifts");
  revalidatePath("/");
  if (shiftId) revalidatePath(`/shifts/${shiftId}`);
}

export async function createShiftAction(_: FormState, formData: FormData): Promise<FormState> {
  const values = formValues(formData);
  const startNow = text(formData, "mode") === "start";
  const op = operation(formData, "planned_operation");
  let shift: Shift;
  try {
    shift = await api.post<Shift>(
      "/shifts",
      compact({
        driver_id: text(formData, "driver_id"),
        vehicle_id: text(formData, "vehicle_id"),
        start_now: startNow,
        start_odometer_km: startNow ? int(formData, "start_odometer_km") : undefined,
        started_at: startNow ? datetime(formData, "started_at") : undefined,
        planned_start_at: startNow ? undefined : datetime(formData, "planned_start_at"),
        planned_end_at: datetime(formData, "planned_end_at"),
        planned_operation_type_id: op.operation_type_id,
        planned_route_id: op.route_id,
        assignment_override_reason: text(formData, "assignment_override_reason"),
        notes: text(formData, "notes"),
      }),
    );
  } catch (error) {
    return errorToFormState(error, values);
  }
  refresh();
  redirect(`/shifts/${shift.id}?notice=created`);
}

async function shiftCall(
  shiftId: string,
  path: string,
  body: unknown,
  values?: Record<string, string>,
): Promise<FormState> {
  try {
    await api.post<Shift>(`/shifts/${shiftId}/${path}`, body);
  } catch (error) {
    return errorToFormState(error, values);
  }
  refresh(shiftId);
  redirect(`/shifts/${shiftId}?notice=${path.replace(/-/g, "_")}`);
}

export async function startShiftAction(
  shiftId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  const op = operation(formData, "operation");
  return shiftCall(
    shiftId,
    "start",
    compact({
      start_odometer_km: int(formData, "start_odometer_km"),
      started_at: datetime(formData, "started_at"),
      assignment_override_reason: text(formData, "assignment_override_reason"),
      operation_type_id: op.operation_type_id,
      route_id: op.route_id,
    }),
    formValues(formData),
  );
}

export async function endShiftAction(
  shiftId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  return shiftCall(
    shiftId,
    "end",
    compact({
      end_odometer_km: int(formData, "end_odometer_km"),
      ended_at: datetime(formData, "ended_at"),
      notes: text(formData, "notes"),
    }),
    formValues(formData),
  );
}

export async function cancelShiftAction(
  shiftId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  return shiftCall(
    shiftId,
    "cancel",
    { reason: text(formData, "reason") ?? "" },
    formValues(formData),
  );
}

export async function correctOdometerAction(
  shiftId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  return shiftCall(
    shiftId,
    "odometer-correction",
    compact({
      start_odometer_km: int(formData, "start_odometer_km"),
      end_odometer_km: int(formData, "end_odometer_km"),
      reason: text(formData, "reason") ?? "",
    }),
    formValues(formData),
  );
}

export async function startSessionAction(
  shiftId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  const op = operation(formData, "operation");
  if (!op.operation_type_id) return { ok: false, fieldErrors: { operation: "اختر نوع التشغيل" } };
  return shiftCall(
    shiftId,
    "sessions",
    compact({
      operation_type_id: op.operation_type_id,
      route_id: op.route_id,
      start_odometer_km: int(formData, "start_odometer_km"),
      notes: text(formData, "notes"),
    }),
    formValues(formData),
  );
}

export async function endSessionAction(sessionId: string, shiftId: string): Promise<FormState> {
  try {
    await api.post(`/operation-sessions/${sessionId}/end`, {});
  } catch (error) {
    return errorToFormState(error);
  }
  refresh(shiftId);
  redirect(`/shifts/${shiftId}?notice=session_ended`);
}

export async function voidRouteEventAction(
  eventId: string,
  shiftId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  try {
    await api.post(`/route-events/${eventId}/void`, { reason: text(formData, "reason") ?? "" });
  } catch (error) {
    return errorToFormState(error);
  }
  refresh(shiftId);
  redirect(`/shifts/${shiftId}?notice=route_event_voided`);
}

export async function addRouteEventAction(
  sessionId: string,
  shiftId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  const values = formValues(formData);
  try {
    await api.post(
      `/operation-sessions/${sessionId}/route-events`,
      compact({
        event_type: text(formData, "event_type"),
        occurred_at: datetime(formData, "occurred_at"),
        reason: text(formData, "reason") ?? "",
      }),
    );
  } catch (error) {
    return errorToFormState(error, values);
  }
  refresh(shiftId);
  redirect(`/shifts/${shiftId}?notice=route_event_added`);
}

export async function recomputeRouteEventsAction(
  sessionId: string,
  shiftId: string,
): Promise<FormState> {
  try {
    await api.post(`/operation-sessions/${sessionId}/route-events/recompute`);
  } catch (error) {
    return errorToFormState(error);
  }
  refresh(shiftId);
  redirect(`/shifts/${shiftId}?notice=route_events_recomputed`);
}
