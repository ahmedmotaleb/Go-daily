"use client";

import { ActionForm } from "@/components/forms/action-form";
import { CheckboxField, SelectField, TextareaField, TextField } from "@/components/forms/fields";
import { options, PAID_BY_LABELS, PAYMENT_METHOD_LABELS, UNIT_LABELS } from "@/lib/finance-labels";
import type { FuelTx } from "@/lib/finance-types";
import type { FormState } from "@/lib/forms";
import { isoToCairoLocal } from "@/lib/time";

type Option = { value: string; label: string };
export type FormMode = "create" | "edit" | "correct";

const LABELS: Record<FormMode, string> = {
  create: "حفظ",
  edit: "حفظ التعديلات",
  correct: "حفظ التصحيح",
};

export function FuelForm({
  action,
  mode,
  vehicles,
  drivers,
  fuelTypes,
  record,
  canApprove,
}: {
  action: (s: FormState, f: FormData) => Promise<FormState>;
  mode: FormMode;
  vehicles: Option[];
  drivers: Option[];
  fuelTypes: Option[];
  record?: FuelTx;
  canApprove: boolean;
}) {
  return (
    <ActionForm
      action={action}
      confirm={
        mode === "correct"
          ? "يُلغى السجل المعتمد وينشأ سجل جديد مرتبط به؛ السجلان محفوظان. متابعة؟"
          : undefined
      }
      submitLabel={LABELS[mode]}
      variant="accent"
      version={record?.updated_at}
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {mode === "edit" ? null : (
          <SelectField
            name="vehicle_id"
            label="المركبة"
            options={vehicles}
            placeholder="اختر المركبة"
            defaultValue={record?.vehicle.id}
            required
          />
        )}
        <SelectField
          name="driver_id"
          label="السائق"
          options={drivers}
          placeholder="بدون"
          defaultValue={record?.driver?.id}
          hint="مطلوب إذا دفع السائق المبلغ"
        />
        <SelectField
          name="fuel_type_id"
          label="النوع"
          options={fuelTypes}
          placeholder="اختر النوع"
          defaultValue={record?.fuel_type.id}
          required
        />
        <TextField
          name="quantity"
          label="الكمية"
          inputMode="decimal"
          defaultValue={record?.quantity}
          required
        />
        <SelectField
          name="unit"
          label="الوحدة"
          options={options(UNIT_LABELS)}
          placeholder="الافتراضية للنوع"
          defaultValue={record?.unit}
        />
        <TextField
          name="unit_price"
          label="سعر الوحدة"
          inputMode="decimal"
          defaultValue={record?.unit_price}
          hint="يكفي إدخال السعر أو الإجمالي"
        />
        <TextField
          name="total_amount"
          label="الإجمالي (جنيه)"
          inputMode="decimal"
          defaultValue={record?.total_amount}
        />
        <TextField
          name="occurred_at"
          label="التاريخ والوقت"
          type="datetime-local"
          defaultValue={isoToCairoLocal(record?.occurred_at)}
          required
        />
        <TextField
          name="odometer_km"
          label="قراءة العداد (كم)"
          inputMode="numeric"
          defaultValue={record?.odometer_km}
        />
        <TextField name="vendor" label="المحطة / المورد" defaultValue={record?.vendor} />
        <SelectField
          name="payment_method"
          label="طريقة الدفع"
          options={options(PAYMENT_METHOD_LABELS, ["PLATFORM"])}
          defaultValue={record?.payment_method ?? "CASH"}
        />
        <SelectField
          name="paid_by"
          label="الدافع"
          options={options(PAID_BY_LABELS)}
          defaultValue={record?.paid_by ?? "COMPANY"}
        />
      </div>
      <TextareaField name="notes" label="ملاحظات" rows={2} defaultValue={record?.notes} />
      {mode === "correct" ? (
        <TextareaField name="reason" label="سبب التصحيح" rows={2} required />
      ) : null}
      {mode !== "edit" && canApprove ? (
        <CheckboxField name="approve_now" label="اعتماد مباشرة (لديك صلاحية الاعتماد)" />
      ) : null}
    </ActionForm>
  );
}
