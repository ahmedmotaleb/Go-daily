import { OWNERSHIP_LABELS_AR, options } from "@go-daily/shared";
import { ActionForm } from "@/components/forms/action-form";
import { SelectField, TextareaField, TextField } from "@/components/forms/fields";
import type { FormState } from "@/lib/forms";
import type { Vehicle, VehicleType } from "@/lib/types";

export function VehicleForm({
  action,
  types,
  vehicle,
}: {
  action: (state: FormState, formData: FormData) => Promise<FormState>;
  types: VehicleType[];
  vehicle?: Vehicle;
}) {
  const typeOptions = types.map((t) => ({ value: t.id, label: t.name_ar }));
  return (
    <ActionForm
      action={action}
      submitLabel={vehicle ? "حفظ التعديلات" : "إضافة المركبة"}
      version={vehicle?.updated_at}
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <TextField
          name="internal_code"
          label="الكود الداخلي"
          defaultValue={vehicle?.internal_code}
          required
          placeholder="GD-001"
          className="ltr-nums"
        />
        <TextField
          name="plate_number"
          label="رقم اللوحة"
          defaultValue={vehicle?.plate_number}
          required
          placeholder="أ ب ج 1234"
        />
        <SelectField
          name="vehicle_type_id"
          label="نوع المركبة"
          defaultValue={vehicle?.vehicle_type.id}
          options={typeOptions}
          placeholder={vehicle ? undefined : "اختر النوع"}
          required
        />
        <TextField
          name="manufacturer"
          label="الشركة المصنعة"
          defaultValue={vehicle?.manufacturer}
        />
        <TextField name="model" label="الموديل" defaultValue={vehicle?.model} />
        <TextField
          name="model_year"
          label="سنة الصنع"
          defaultValue={vehicle?.model_year}
          inputMode="numeric"
        />
        <TextField name="color" label="اللون" defaultValue={vehicle?.color} />
        <SelectField
          name="ownership_status"
          label="حالة الملكية"
          defaultValue={vehicle?.ownership_status ?? "OWNED"}
          options={options(OWNERSHIP_LABELS_AR)}
          required
        />
        <TextField
          name="current_odometer_km"
          label="قراءة العداد الحالية (كم)"
          defaultValue={vehicle?.current_odometer_km}
          inputMode="numeric"
        />
        <TextField
          name="license_expiry"
          label="انتهاء الرخصة"
          type="date"
          defaultValue={vehicle?.license_expiry}
        />
        <TextField
          name="insurance_expiry"
          label="انتهاء التأمين"
          type="date"
          defaultValue={vehicle?.insurance_expiry}
        />
        {vehicle ? (
          <TextField
            name="odometer_correction_reason"
            label="سبب تصحيح العداد"
            hint="مطلوب فقط عند تقليل قراءة العداد"
          />
        ) : null}
      </div>
      <TextareaField name="notes" label="ملاحظات" defaultValue={vehicle?.notes} />
    </ActionForm>
  );
}
