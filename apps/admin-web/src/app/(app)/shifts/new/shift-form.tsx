"use client";

import { useState } from "react";
import { ActionForm } from "@/components/forms/action-form";
import { SelectField, TextareaField, TextField } from "@/components/forms/fields";
import type { FormState } from "@/lib/forms";

type Option = { value: string; label: string };

export function ShiftForm({
  action,
  drivers,
  vehicles,
  operations,
}: {
  action: (s: FormState, f: FormData) => Promise<FormState>;
  drivers: Option[];
  vehicles: Option[];
  operations: Option[];
}) {
  const [mode, setMode] = useState<"plan" | "start">("start");
  return (
    <ActionForm
      action={action}
      submitLabel={mode === "start" ? "بدء الوردية الآن" : "حفظ الوردية المخططة"}
      variant="accent"
    >
      <fieldset className="flex flex-wrap gap-4">
        <legend className="sr-only">نوع الإجراء</legend>
        {(
          [
            ["start", "بدء الآن"],
            ["plan", "تخطيط لوقت لاحق"],
          ] as const
        ).map(([value, label]) => (
          <label key={value} className="inline-flex items-center gap-2 text-sm font-medium">
            <input
              type="radio"
              name="mode"
              value={value}
              checked={mode === value}
              onChange={() => setMode(value)}
              className="size-4 accent-forest-700"
            />
            {label}
          </label>
        ))}
      </fieldset>
      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField
          name="driver_id"
          label="السائق"
          options={drivers}
          placeholder="اختر السائق"
          required
        />
        <SelectField
          name="vehicle_id"
          label="المركبة"
          options={vehicles}
          placeholder="اختر المركبة"
          required
        />
        {mode === "start" ? (
          <>
            <TextField
              name="start_odometer_km"
              label="قراءة العداد عند البدء (كم)"
              inputMode="numeric"
              required
            />
            <TextField
              name="started_at"
              label="وقت البدء"
              type="datetime-local"
              hint="اتركه فارغًا للآن"
            />
          </>
        ) : (
          <>
            <TextField name="planned_start_at" label="البداية المخططة" type="datetime-local" />
            <TextField name="planned_end_at" label="النهاية المخططة" type="datetime-local" />
          </>
        )}
        <SelectField
          name="planned_operation"
          label={mode === "start" ? "التشغيل الأول" : "التشغيل المخطط"}
          options={operations}
          placeholder="بدون (يمكن تحديده لاحقًا)"
        />
        <TextField
          name="assignment_override_reason"
          label="سبب الاستثناء (إن لم يكن السائق مكلفًا بالمركبة)"
          hint="مطلوب فقط عند تشغيل سائق غير مكلف بهذه المركبة"
        />
      </div>
      <TextareaField name="notes" label="ملاحظات" rows={2} />
    </ActionForm>
  );
}
