"use client";

import { ActionForm } from "@/components/forms/action-form";
import { CheckboxField, SelectField, TextareaField, TextField } from "@/components/forms/fields";
import { options, PAID_BY_LABELS, PAYMENT_METHOD_LABELS } from "@/lib/finance-labels";
import type { Expense } from "@/lib/finance-types";
import type { FormState } from "@/lib/forms";
import { isoToCairoLocal } from "@/lib/time";
import type { FormMode } from "./fuel-form";

type Option = { value: string; label: string };

export function ExpenseForm({
  action,
  mode,
  vehicles,
  drivers,
  categories,
  record,
  canApprove,
}: {
  action: (s: FormState, f: FormData) => Promise<FormState>;
  mode: FormMode;
  vehicles: Option[];
  drivers: Option[];
  categories: Option[];
  record?: Expense;
  canApprove: boolean;
}) {
  return (
    <ActionForm
      action={action}
      submitLabel={mode === "create" ? "حفظ" : mode === "edit" ? "حفظ التعديلات" : "حفظ التصحيح"}
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
          name="category_id"
          label="التصنيف"
          options={categories}
          placeholder="اختر التصنيف"
          defaultValue={record?.category.id}
          required
        />
        <TextField
          name="amount"
          label="المبلغ (جنيه)"
          inputMode="decimal"
          defaultValue={record?.amount}
          required
        />
        <TextField
          name="occurred_at"
          label="التاريخ والوقت"
          type="datetime-local"
          defaultValue={isoToCairoLocal(record?.occurred_at)}
          required
        />
        <SelectField
          name="driver_id"
          label="السائق"
          options={drivers}
          placeholder="بدون"
          defaultValue={record?.driver?.id}
        />
        <TextField name="vendor" label="المورد / الجهة" defaultValue={record?.vendor} />
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
