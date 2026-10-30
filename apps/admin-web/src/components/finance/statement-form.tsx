"use client";

import { ActionForm } from "@/components/forms/action-form";
import { CheckboxField, SelectField, TextareaField, TextField } from "@/components/forms/fields";
import { options, RECEIVED_BY_LABELS } from "@/lib/finance-labels";
import type { Statement } from "@/lib/finance-types";
import type { FormState } from "@/lib/forms";
import type { FormMode } from "./fuel-form";

type Option = { value: string; label: string };

export function StatementForm({
  action,
  mode,
  platforms,
  vehicles,
  drivers,
  record,
  canApprove,
}: {
  action: (s: FormState, f: FormData) => Promise<FormState>;
  mode: FormMode;
  platforms: Option[];
  vehicles: Option[];
  drivers: Option[];
  record?: Statement;
  canApprove: boolean;
}) {
  return (
    <ActionForm
      action={action}
      submitLabel={
        mode === "create" ? "حفظ الكشف" : mode === "edit" ? "حفظ التعديلات" : "حفظ التصحيح"
      }
      variant="accent"
      version={record?.updated_at}
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <SelectField
          name="platform_id"
          label="المنصة"
          options={platforms}
          placeholder="اختر المنصة"
          defaultValue={record?.platform.id}
          required
        />
        <SelectField
          name="driver_id"
          label="السائق"
          options={drivers}
          placeholder="اختر السائق"
          defaultValue={record?.driver.id}
          required
        />
        <SelectField
          name="vehicle_id"
          label="المركبة"
          options={vehicles}
          placeholder="اختر المركبة"
          defaultValue={record?.vehicle.id}
          required
        />
        <TextField
          name="period_start"
          label="بداية الفترة"
          type="date"
          defaultValue={record?.period_start}
          required
        />
        <TextField
          name="period_end"
          label="نهاية الفترة"
          type="date"
          defaultValue={record?.period_end}
          required
        />
        <TextField
          name="trips_count"
          label="عدد الرحلات"
          inputMode="numeric"
          defaultValue={record?.trips_count}
        />
        <TextField
          name="gross_earnings"
          label="إجمالي الأجرة"
          inputMode="decimal"
          defaultValue={record?.gross_earnings}
          required
        />
        <TextField
          name="platform_fees"
          label="عمولة ورسوم المنصة"
          inputMode="decimal"
          defaultValue={record?.platform_fees}
          required
        />
        <TextField
          name="tips"
          label="إكراميات"
          inputMode="decimal"
          defaultValue={record?.tips ?? "0"}
        />
        <TextField
          name="adjustments"
          label="حوافز (+) / تسويات (−)"
          inputMode="decimal"
          defaultValue={record?.adjustments ?? "0"}
        />
        <TextField
          name="cash_collected"
          label="نقدي حصّله السائق من الركاب"
          inputMode="decimal"
          defaultValue={record?.cash_collected ?? "0"}
        />
        <SelectField
          name="payout_recipient"
          label="مستلم تحويل المنصة"
          options={options(RECEIVED_BY_LABELS)}
          defaultValue={record?.payout_recipient ?? "DRIVER"}
        />
        <TextField
          name="statement_reference"
          label="رقم/مرجع الكشف"
          defaultValue={record?.statement_reference}
        />
      </div>
      <TextareaField name="notes" label="ملاحظات" rows={2} defaultValue={record?.notes} />
      {mode === "correct" ? (
        <TextareaField name="reason" label="سبب التصحيح" rows={2} required />
      ) : null}
      {mode !== "edit" && canApprove ? (
        <CheckboxField name="approve_now" label="اعتماد مباشرة وإنشاء الإيراد" />
      ) : null}
    </ActionForm>
  );
}
