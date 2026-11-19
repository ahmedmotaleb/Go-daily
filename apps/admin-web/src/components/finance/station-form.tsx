"use client";

import { ActionForm } from "@/components/forms/action-form";
import { CheckboxField, TextareaField, TextField } from "@/components/forms/fields";
import type { FuelStation, FuelType } from "@/lib/finance-types";
import type { FormState } from "@/lib/forms";

export function StationForm({
  action,
  fuelTypes,
  station,
}: {
  action: (s: FormState, f: FormData) => Promise<FormState>;
  fuelTypes: FuelType[];
  station?: FuelStation;
}) {
  const sold = new Set(station?.fuel_types.map((t) => t.id));
  return (
    <ActionForm
      action={action}
      submitLabel={station ? "حفظ التعديلات" : "إضافة محطة"}
      variant={station ? "accent" : "secondary"}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField name="name" label="اسم المحطة" defaultValue={station?.name} required />
        <TextField name="brand" label="الشركة" defaultValue={station?.brand} />
        <TextField name="address" label="العنوان" defaultValue={station?.address} />
        <TextField
          name="radius_m"
          label="نطاق المحطة (متر)"
          inputMode="numeric"
          defaultValue={station?.radius_m ?? 150}
          hint="بين 20 و5000"
        />
        <TextField
          name="latitude"
          label="خط العرض"
          inputMode="decimal"
          defaultValue={station?.latitude ?? undefined}
        />
        <TextField
          name="longitude"
          label="خط الطول"
          inputMode="decimal"
          defaultValue={station?.longitude ?? undefined}
        />
      </div>
      <fieldset className="space-y-2">
        <legend className="mb-1 text-sm font-medium">الأنواع المتاحة</legend>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          {fuelTypes.map((t) => (
            <CheckboxField
              key={t.id}
              name={`fuel_type:${t.id}`}
              label={t.name_ar}
              defaultChecked={sold.has(t.id)}
            />
          ))}
        </div>
      </fieldset>
      <CheckboxField
        name="is_trusted"
        label="محطة موثوقة: تُربط بها تلقائيًا مشتريات السائقين داخل نطاقها (تحتاج موقعًا)"
        defaultChecked={station?.is_trusted}
      />
      <TextareaField name="notes" label="ملاحظات" rows={2} defaultValue={station?.notes} />
    </ActionForm>
  );
}
