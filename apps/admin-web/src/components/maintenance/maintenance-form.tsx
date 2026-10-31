"use client";

import type { FormMode } from "@/components/finance/fuel-form";
import { ActionForm } from "@/components/forms/action-form";
import { CheckboxField, SelectField, TextareaField, TextField } from "@/components/forms/fields";
import type { FormState } from "@/lib/forms";
import type { MaintenanceRecord } from "@/lib/maintenance-types";
import { isoToCairoLocal } from "@/lib/time";

type Option = { value: string; label: string };

export function MaintenanceForm({
  action,
  mode,
  vehicles,
  types,
  oilPurchases = [],
  record,
  canApprove,
  defaultVehicleId,
}: {
  action: (s: FormState, f: FormData) => Promise<FormState>;
  mode: FormMode;
  vehicles: Option[];
  types: Option[];
  /** Consumable purchases of this vehicle that can be linked (edit/correct). */
  oilPurchases?: Option[];
  record?: MaintenanceRecord;
  canApprove: boolean;
  defaultVehicleId?: string;
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
      {mode === "edit" ? (
        <input type="hidden" name="vehicle_id" value={record?.vehicle.id} />
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {mode === "edit" ? null : (
          <SelectField
            name="vehicle_id"
            label="المركبة"
            options={vehicles}
            placeholder="اختر المركبة"
            defaultValue={record?.vehicle.id ?? defaultVehicleId}
            required
          />
        )}
        <SelectField
          name="type_id"
          label="نوع الصيانة"
          options={types}
          placeholder="اختر النوع"
          defaultValue={record?.type.id}
          required
        />
        <TextField
          name="performed_on"
          label="تاريخ التنفيذ"
          type="date"
          defaultValue={record?.performed_on}
          required
        />
        <TextField
          name="odometer_km"
          label="قراءة العداد (كم)"
          inputMode="numeric"
          defaultValue={record?.odometer_km}
          hint="تُستخدم لحساب موعد الصيانة التالية"
        />
        <TextField name="vendor" label="الورشة / المورد" defaultValue={record?.vendor} />
        <TextField
          name="parts_cost"
          label="قطع الغيار"
          inputMode="decimal"
          defaultValue={record?.parts_cost ?? "0"}
        />
        <TextField
          name="labor_cost"
          label="المصنعية"
          inputMode="decimal"
          defaultValue={record?.labor_cost ?? "0"}
        />
        <TextField
          name="other_cost"
          label="تكاليف أخرى"
          inputMode="decimal"
          defaultValue={record?.other_cost ?? "0"}
        />
        <TextField
          name="downtime_start"
          label="بداية توقف المركبة"
          type="datetime-local"
          defaultValue={isoToCairoLocal(record?.downtime_start)}
        />
        <TextField
          name="downtime_end"
          label="نهاية التوقف"
          type="datetime-local"
          defaultValue={isoToCairoLocal(record?.downtime_end)}
        />
        {oilPurchases.length ? (
          <SelectField
            name="fuel_transaction_id"
            label="ربط بشراء زيت/مستهلكات"
            options={oilPurchases}
            placeholder="بدون ربط"
            defaultValue={record?.fuel_transaction_id}
            hint="شراء الزيت سجل وقود؛ التغيير سجل صيانة"
          />
        ) : null}
      </div>
      <TextareaField
        name="description"
        label="الأعمال المنفذة"
        rows={2}
        defaultValue={record?.description}
      />
      <TextareaField name="notes" label="ملاحظات" rows={2} defaultValue={record?.notes} />
      {mode === "correct" ? (
        <TextareaField name="reason" label="سبب التصحيح" rows={2} required />
      ) : null}
      {mode !== "edit" && canApprove ? (
        <CheckboxField name="approve_now" label="اعتماد التكلفة مباشرة (لديك صلاحية الاعتماد)" />
      ) : null}
    </ActionForm>
  );
}
