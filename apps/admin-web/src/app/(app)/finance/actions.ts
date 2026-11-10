"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { boundId, boundOneOf } from "@/lib/bound";
import { errorToFormState, formValues } from "@/lib/form-state";
import type { FormState } from "@/lib/forms";
import { FINANCE_PAGE, type FinanceResource as Resource } from "@/lib/finance-paths";
import type { NoticeCode } from "@/lib/notices";
import {
  checkbox,
  compact,
  datetime,
  decimal,
  int,
  intOrNull,
  text,
  textOrNull,
} from "@/lib/parse";

type Mode = "create" | "edit" | "correct";

const API_PATH: Record<Resource, string> = {
  fuel: "/fuel",
  expenses: "/expenses",
  revenue: "/revenue",
  statements: "/ride-hailing/statements",
  maintenance: "/maintenance/records",
};

function refresh(resource: Resource, id?: string) {
  revalidatePath(FINANCE_PAGE[resource]);
  if (resource === "maintenance") revalidatePath("/maintenance");
  revalidatePath("/finance/profitability");
  if (id) revalidatePath(`${FINANCE_PAGE[resource]}/${id}`);
}

function go(resource: Resource, id: string, notice: NoticeCode): never {
  redirect(`${FINANCE_PAGE[resource]}/${id}?notice=${notice}`);
}

/** POST/PATCH/PUT and redirect to the record (new record for corrections). */
async function save(
  resource: Resource,
  mode: Mode,
  id: string | null,
  body: Record<string, unknown>,
  values: Record<string, string>,
  editMethod: "patch" | "put" = "patch",
): Promise<FormState> {
  mode = boundOneOf(mode, ["create", "edit", "correct"] as const);
  const base = API_PATH[resource];
  if (id !== null) id = boundId(id);
  let saved: { id: string };
  try {
    if (mode === "create") saved = await api.post(base, body);
    else if (mode === "correct") saved = await api.post(`${base}/${id}/correct`, body);
    else if (editMethod === "put") saved = await api.put(`${base}/${id}`, body);
    else saved = await api.patch(`${base}/${id}`, body);
  } catch (error) {
    return errorToFormState(error, values);
  }
  refresh(resource, saved.id);
  if (id) refresh(resource, id);
  go(
    resource,
    saved.id,
    mode === "create" ? "created" : mode === "correct" ? "record_correct" : "record_updated",
  );
}

function lifecycle(formData: FormData, mode: Mode) {
  return compact({
    approve_now: mode === "edit" ? undefined : checkbox(formData, "approve_now"),
    reason: mode === "correct" ? (text(formData, "reason") ?? "") : undefined,
  });
}

export async function reviewAction(
  resource: Resource,
  id: string,
  op: "approve" | "reject" | "void",
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  resource = boundOneOf(resource, Object.keys(API_PATH) as Resource[]);
  id = boundId(id);
  op = boundOneOf(op, ["approve", "reject", "void"] as const);
  const body =
    op === "approve"
      ? compact({ note: text(formData, "note") })
      : { reason: text(formData, "reason") ?? "" };
  try {
    await api.post(`${API_PATH[resource]}/${id}/${op}`, body);
  } catch (error) {
    return errorToFormState(error, formValues(formData));
  }
  refresh(resource, id);
  go(resource, id, `record_${op}`);
}

// --- Fuel ------------------------------------------------------------------------

export async function saveFuelAction(
  mode: Mode,
  id: string | null,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  const common = {
    fuel_type_id: text(formData, "fuel_type_id"),
    quantity: decimal(formData, "quantity"),
    unit: text(formData, "unit"),
    unit_price: decimal(formData, "unit_price"),
    total_amount: decimal(formData, "total_amount"),
    occurred_at: datetime(formData, "occurred_at"),
    payment_method: text(formData, "payment_method"),
    paid_by: text(formData, "paid_by"),
  };
  const body =
    mode === "edit"
      ? {
          ...compact(common),
          driver_id: textOrNull(formData, "driver_id"),
          odometer_km: intOrNull(formData, "odometer_km"),
          vendor: textOrNull(formData, "vendor"),
          notes: textOrNull(formData, "notes"),
        }
      : compact({
          ...common,
          vehicle_id: text(formData, "vehicle_id"),
          driver_id: text(formData, "driver_id"),
          odometer_km: int(formData, "odometer_km"),
          vendor: text(formData, "vendor"),
          notes: text(formData, "notes"),
          ...lifecycle(formData, mode),
        });
  return save("fuel", mode, id, body, formValues(formData));
}

// --- Expenses ----------------------------------------------------------------------

export async function saveExpenseAction(
  mode: Mode,
  id: string | null,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  const common = {
    category_id: text(formData, "category_id"),
    amount: decimal(formData, "amount"),
    occurred_at: datetime(formData, "occurred_at"),
    payment_method: text(formData, "payment_method"),
    paid_by: text(formData, "paid_by"),
  };
  const body =
    mode === "edit"
      ? {
          ...compact(common),
          driver_id: textOrNull(formData, "driver_id"),
          vendor: textOrNull(formData, "vendor"),
          notes: textOrNull(formData, "notes"),
        }
      : compact({
          ...common,
          vehicle_id: text(formData, "vehicle_id"),
          driver_id: text(formData, "driver_id"),
          vendor: text(formData, "vendor"),
          notes: text(formData, "notes"),
          ...lifecycle(formData, mode),
        });
  return save("expenses", mode, id, body, formValues(formData));
}

// --- Revenue ---------------------------------------------------------------------------

function receiptBody(formData: FormData, prefix = "") {
  return compact({
    amount: decimal(formData, `${prefix}amount`),
    received_at: datetime(formData, `${prefix}received_at`) ?? new Date().toISOString(),
    method: text(formData, `${prefix}method`),
    received_by: text(formData, `${prefix}received_by`),
    reference: text(formData, `${prefix}reference`),
  });
}

export async function saveRevenueAction(
  mode: Mode,
  id: string | null,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  const fields = {
    driver_id: text(formData, "driver_id"),
    operation_type_id: text(formData, "operation_type_id"),
    occurred_on: text(formData, "occurred_on"),
    period_start: text(formData, "period_start"),
    period_end: text(formData, "period_end"),
    amount: decimal(formData, "amount"),
    loops_count: int(formData, "loops_count"),
    customer_name: text(formData, "customer_name"),
    reference: text(formData, "reference"),
    notes: text(formData, "notes"),
  };
  let body: Record<string, unknown>;
  if (mode === "edit") {
    body = {
      ...compact({ occurred_on: fields.occurred_on, amount: fields.amount }),
      driver_id: textOrNull(formData, "driver_id"),
      operation_type_id: textOrNull(formData, "operation_type_id"),
      period_start: textOrNull(formData, "period_start"),
      period_end: textOrNull(formData, "period_end"),
      loops_count: intOrNull(formData, "loops_count"),
      customer_name: textOrNull(formData, "customer_name"),
      reference: textOrNull(formData, "reference"),
      notes: textOrNull(formData, "notes"),
    };
  } else {
    const withReceipt = mode === "create" && decimal(formData, "receipt_amount") !== undefined;
    body = compact({
      kind: text(formData, "kind"),
      vehicle_id: text(formData, "vehicle_id"),
      ...fields,
      receipt: withReceipt ? receiptBody(formData, "receipt_") : undefined,
      ...lifecycle(formData, mode),
    });
  }
  return save("revenue", mode, id, body, formValues(formData));
}

export async function addReceiptAction(
  entryId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  entryId = boundId(entryId);
  try {
    await api.post(`/revenue/${entryId}/receipts`, receiptBody(formData));
  } catch (error) {
    return errorToFormState(error, formValues(formData));
  }
  refresh("revenue", entryId);
  go("revenue", entryId, "receipt_added");
}

export async function voidReceiptAction(
  receiptId: string,
  entryId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  receiptId = boundId(receiptId);
  entryId = boundId(entryId);
  try {
    await api.post(`/revenue/receipts/${receiptId}/void`, {
      reason: text(formData, "reason") ?? "",
    });
  } catch (error) {
    return errorToFormState(error, formValues(formData));
  }
  refresh("revenue", entryId);
  go("revenue", entryId, "receipt_voided");
}

// --- Ride-hailing statements ---------------------------------------------------------

export async function saveStatementAction(
  mode: Mode,
  id: string | null,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  const body = compact({
    platform_id: text(formData, "platform_id"),
    driver_id: text(formData, "driver_id"),
    vehicle_id: text(formData, "vehicle_id"),
    period_start: text(formData, "period_start"),
    period_end: text(formData, "period_end"),
    trips_count: int(formData, "trips_count"),
    gross_earnings: decimal(formData, "gross_earnings"),
    platform_fees: decimal(formData, "platform_fees"),
    tips: decimal(formData, "tips") ?? "0",
    adjustments: decimal(formData, "adjustments") ?? "0",
    cash_collected: decimal(formData, "cash_collected") ?? "0",
    payout_recipient: text(formData, "payout_recipient"),
    statement_reference: text(formData, "statement_reference"),
    notes: text(formData, "notes"),
    ...lifecycle(formData, mode),
  });
  return save("statements", mode, id, body, formValues(formData), "put");
}

// --- Driver account & settlements -----------------------------------------------------

export async function addLedgerEntryAction(
  driverId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  driverId = boundId(driverId);
  const values = formValues(formData);
  try {
    await api.post(
      `/drivers/${driverId}/ledger`,
      compact({
        entry_type: text(formData, "entry_type"),
        amount: decimal(formData, "amount"),
        occurred_on: text(formData, "occurred_on"),
        description: text(formData, "description"),
        direction: text(formData, "direction"),
        reason: text(formData, "reason"),
      }),
    );
  } catch (error) {
    return errorToFormState(error, values);
  }
  revalidatePath(`/drivers/${driverId}/account`);
  redirect(`/drivers/${driverId}/account?notice=ledger_added`);
}

export async function voidLedgerEntryAction(
  entryId: string,
  driverId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  entryId = boundId(entryId);
  driverId = boundId(driverId);
  try {
    await api.post(`/driver-ledger/${entryId}/void`, { reason: text(formData, "reason") ?? "" });
  } catch (error) {
    return errorToFormState(error, formValues(formData));
  }
  revalidatePath(`/drivers/${driverId}/account`);
  redirect(`/drivers/${driverId}/account?notice=ledger_voided`);
}

export async function createSettlementAction(_: FormState, formData: FormData): Promise<FormState> {
  let created: { id: string };
  try {
    created = await api.post(
      "/settlements",
      compact({
        driver_id: text(formData, "driver_id"),
        period_start: text(formData, "period_start"),
        period_end: text(formData, "period_end"),
        notes: text(formData, "notes"),
      }),
    );
  } catch (error) {
    return errorToFormState(error, formValues(formData));
  }
  revalidatePath("/finance/settlements");
  redirect(`/finance/settlements/${created.id}?notice=created`);
}

export async function settlementAction(
  id: string,
  op: "finalize" | "recalculate" | "void",
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  id = boundId(id);
  op = boundOneOf(op, ["finalize", "recalculate", "void"] as const);
  try {
    await api.post(
      `/settlements/${id}/${op}`,
      op === "void" ? { reason: text(formData, "reason") ?? "" } : undefined,
    );
  } catch (error) {
    return errorToFormState(error, formValues(formData));
  }
  revalidatePath("/finance/settlements");
  revalidatePath(`/finance/settlements/${id}`);
  redirect(`/finance/settlements/${id}?notice=settlement_${op}`);
}

// --- Finance settings ---------------------------------------------------------------------

type SettingsKind = "platforms" | "fuel-types" | "expense-categories";
const SETTINGS_PATH: Record<SettingsKind, string> = {
  platforms: "/ride-hailing/platforms",
  "fuel-types": "/fuel-types",
  "expense-categories": "/expense-categories",
};

export async function createSettingAction(
  kind: SettingsKind,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  kind = boundOneOf(kind, Object.keys(SETTINGS_PATH) as SettingsKind[]);
  const body =
    kind === "platforms"
      ? compact({ name: text(formData, "name"), notes: text(formData, "notes") })
      : compact({
          code: text(formData, "code")?.toUpperCase(),
          name_ar: text(formData, "name_ar"),
          category: text(formData, "category"),
          default_unit: text(formData, "default_unit"),
          pnl_group: text(formData, "pnl_group"),
        });
  try {
    await api.post(SETTINGS_PATH[kind], body);
  } catch (error) {
    return errorToFormState(error, formValues(formData));
  }
  revalidatePath("/finance/settings");
  redirect("/finance/settings?notice=created");
}

export async function toggleSettingAction(
  kind: SettingsKind,
  id: string,
  active: boolean,
  _state: FormState,
  _formData: FormData,
): Promise<FormState> {
  kind = boundOneOf(kind, Object.keys(SETTINGS_PATH) as SettingsKind[]);
  id = boundId(id);
  try {
    await api.patch(`${SETTINGS_PATH[kind]}/${id}`, { is_active: active === true });
  } catch (error) {
    return errorToFormState(error);
  }
  revalidatePath("/finance/settings");
  redirect("/finance/settings?notice=record_updated");
}

// --- Maintenance ----------------------------------------------------------------------

export async function saveMaintenanceAction(
  mode: Mode,
  id: string | null,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  const body = {
    ...compact({
      vehicle_id: text(formData, "vehicle_id"),
      type_id: text(formData, "type_id"),
      performed_on: text(formData, "performed_on"),
      odometer_km: int(formData, "odometer_km"),
      vendor: text(formData, "vendor"),
      parts_cost: decimal(formData, "parts_cost") ?? "0",
      labor_cost: decimal(formData, "labor_cost") ?? "0",
      other_cost: decimal(formData, "other_cost") ?? "0",
      description: text(formData, "description"),
      downtime_start: datetime(formData, "downtime_start"),
      downtime_end: datetime(formData, "downtime_end"),
      fuel_transaction_id: text(formData, "fuel_transaction_id"),
      notes: text(formData, "notes"),
    }),
    ...lifecycle(formData, mode),
  };
  return save("maintenance", mode, id, body, formValues(formData), "put");
}

export async function saveScheduleAction(
  vehicleId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  vehicleId = boundId(vehicleId);
  try {
    await api.put(
      `/maintenance/vehicles/${vehicleId}/schedules`,
      compact({
        type_id: text(formData, "type_id"),
        interval_km: int(formData, "interval_km"),
        interval_days: int(formData, "interval_days"),
        baseline_km: int(formData, "baseline_km"),
        baseline_date: text(formData, "baseline_date"),
        is_active: text(formData, "is_active") !== "false",
      }),
    );
  } catch (error) {
    return errorToFormState(error, formValues(formData));
  }
  revalidatePath(`/vehicles/${vehicleId}`);
  revalidatePath("/maintenance");
  redirect(`/vehicles/${vehicleId}?notice=schedule_saved`);
}
