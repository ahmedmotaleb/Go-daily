"use client";

import { ActionForm } from "@/components/forms/action-form";
import { CheckboxField, SelectField, TextareaField, TextField } from "@/components/forms/fields";
import {
  options,
  PAYMENT_METHOD_LABELS,
  RECEIVED_BY_LABELS,
  REVENUE_KIND_LABELS,
} from "@/lib/finance-labels";
import type { RevenueEntry } from "@/lib/finance-types";
import type { FormState } from "@/lib/forms";
import type { FormMode } from "./fuel-form";

type Option = { value: string; label: string };

export function RevenueForm({
  action,
  mode,
  vehicles,
  drivers,
  operationTypes,
  record,
  canApprove,
}: {
  action: (s: FormState, f: FormData) => Promise<FormState>;
  mode: FormMode;
  vehicles: Option[];
  drivers: Option[];
  operationTypes: Option[];
  record?: RevenueEntry;
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
      submitLabel={mode === "create" ? "حفظ" : mode === "edit" ? "حفظ التعديلات" : "حفظ التصحيح"}
      variant="accent"
      version={record?.updated_at}
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {mode === "edit" ? null : (
          <>
            <SelectField
              name="kind"
              label="نوع الإيراد"
              options={options(REVENUE_KIND_LABELS, ["RIDE_HAILING"])}
              placeholder="اختر"
              defaultValue={record?.kind}
              hint="إيراد النقل الذكي يُسجل من كشوف المنصات"
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
          </>
        )}
        <SelectField
          name="driver_id"
          label="السائق"
          options={drivers}
          placeholder="بدون"
          defaultValue={record?.driver?.id}
          hint="مطلوب إذا استلم السائق المبلغ"
        />
        <SelectField
          name="operation_type_id"
          label="نوع التشغيل"
          options={operationTypes}
          placeholder="غير محدد"
          defaultValue={record?.operation_type?.id}
        />
        <TextField
          name="occurred_on"
          label="تاريخ الإيراد"
          type="date"
          defaultValue={record?.occurred_on}
          required
        />
        <TextField
          name="amount"
          label="المبلغ المستحق (جنيه)"
          inputMode="decimal"
          defaultValue={record?.amount}
          required
        />
        <TextField
          name="period_start"
          label="بداية فترة الخدمة"
          type="date"
          defaultValue={record?.period_start}
          hint="للعقود: يوزَّع المبلغ على أيام الفترة"
        />
        <TextField
          name="period_end"
          label="نهاية فترة الخدمة"
          type="date"
          defaultValue={record?.period_end}
        />
        <TextField
          name="loops_count"
          label="عدد الدورات (اختياري)"
          inputMode="numeric"
          defaultValue={record?.loops_count}
        />
        <TextField
          name="customer_name"
          label="العميل / الجهة"
          defaultValue={record?.customer_name}
        />
        <TextField name="reference" label="مرجع" defaultValue={record?.reference} />
      </div>
      <TextareaField name="notes" label="ملاحظات" rows={2} defaultValue={record?.notes} />
      {mode === "create" ? (
        <fieldset className="rounded-[var(--radius-control)] border border-line p-4">
          <legend className="px-1 text-sm font-semibold">المبلغ المستلم الآن (اختياري)</legend>
          <div className="grid gap-4 sm:grid-cols-3">
            <TextField name="receipt_amount" label="المبلغ المستلم" inputMode="decimal" />
            <SelectField
              name="receipt_method"
              label="طريقة الاستلام"
              options={options(PAYMENT_METHOD_LABELS, ["PLATFORM"])}
              defaultValue="CASH"
            />
            <SelectField
              name="receipt_received_by"
              label="المستلم"
              options={options(RECEIVED_BY_LABELS)}
              defaultValue="DRIVER"
            />
          </div>
        </fieldset>
      ) : null}
      {mode === "correct" ? (
        <TextareaField
          name="reason"
          label="سبب التصحيح"
          rows={2}
          hint="المبالغ المستلمة تنتقل إلى السجل المصحح"
          required
        />
      ) : null}
      {mode !== "edit" && canApprove ? (
        <CheckboxField name="approve_now" label="اعتماد مباشرة (لديك صلاحية الاعتماد)" />
      ) : null}
    </ActionForm>
  );
}

export function ReceiptForm({
  action,
  hasDriver,
}: {
  action: (s: FormState, f: FormData) => Promise<FormState>;
  hasDriver: boolean;
}) {
  return (
    <ActionForm action={action} submitLabel="تسجيل المبلغ" variant="accent">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <TextField name="amount" label="المبلغ" inputMode="decimal" required />
        <TextField
          name="received_at"
          label="وقت الاستلام"
          type="datetime-local"
          hint="فارغ = الآن"
        />
        <SelectField
          name="method"
          label="الطريقة"
          options={options(PAYMENT_METHOD_LABELS, ["PLATFORM"])}
          defaultValue="CASH"
        />
        <SelectField
          name="received_by"
          label="المستلم"
          options={options(RECEIVED_BY_LABELS, hasDriver ? [] : ["DRIVER"])}
          defaultValue={hasDriver ? "DRIVER" : "COMPANY"}
        />
      </div>
      <TextField name="reference" label="مرجع (اختياري)" />
    </ActionForm>
  );
}
